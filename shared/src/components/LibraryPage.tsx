import { useState, useEffect, useCallback, useRef } from "react";
import type { JournalClubApi, ArticleWithMeta, ApiError as ApiErrorType } from "../api";
import type { HistoryItem } from "../types";

interface Props {
  api: JournalClubApi;
  refreshKey?: number;
  onSignOut?: () => void;
  /** Desktop only: callback to open the Add Article modal */
  onAddArticle?: () => void;
  /** Desktop only: open PDF bytes in the system viewer (sidesteps WebView2 blob/iframe CSP) */
  openPdfExternal?: (bytes: Uint8Array, filename: string) => Promise<void>;
}

type Tab = "downloaded" | "queued";

export function LibraryPage({ api, refreshKey, onSignOut, onAddArticle, openPdfExternal }: Props) {
  const [tab, setTab] = useState<Tab>("downloaded");

  // ── Downloaded tab state ───────────────────────────────────────────────────
  const [articles, setArticles] = useState<ArticleWithMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [loadingArticles, setLoadingArticles] = useState(true);
  const [articleError, setArticleError] = useState<string | null>(null);
  const [, setAllTags] = useState<string[]>([]);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [emailMode, setEmailMode] = useState(false);
  const [emailSelected, setEmailSelected] = useState<Set<string>>(new Set());
  const [emailSending, setEmailSending] = useState(false);
  const [emailStatus, setEmailStatus] = useState<string | null>(null);
  const [expandedArticle, setExpandedArticle] = useState<string | null>(null);

  // ── Queued/History tab state ───────────────────────────────────────────────
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const historyOffsetRef = useRef(0);
  const [expandedHistory, setExpandedHistory] = useState<string | null>(null);
  const HISTORY_LIMIT = 50;

  // ── Debounce search ────────────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  // ── Fetch downloaded articles ──────────────────────────────────────────────
  const fetchArticles = useCallback(async () => {
    setLoadingArticles(true);
    setArticleError(null);
    try {
      const res = await api.getArticles({ q: debouncedQuery || undefined, selected_only: selectedOnly || undefined, limit: 100 });
      setArticles(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      const e = err as ApiErrorType;
      if (e?.status === 401 && onSignOut) { onSignOut(); return; }
      setArticleError(e?.message ?? "Failed to load articles");
    } finally {
      setLoadingArticles(false);
    }
  }, [debouncedQuery, selectedOnly, onSignOut, api]);

  useEffect(() => { fetchArticles(); }, [fetchArticles, refreshKey]);
  useEffect(() => { api.getTags().then(setAllTags).catch(() => {}); }, [articles, api]);

  // ── Fetch history ──────────────────────────────────────────────────────────
  const loadHistory = useCallback(async (reset = false) => {
    setHistoryLoading(true);
    const off = reset ? 0 : historyOffsetRef.current;
    try {
      const data = await api.getHistory(HISTORY_LIMIT, off);
      setHistoryItems(prev => reset ? data : [...prev, ...data]);
      setHasMoreHistory(data.length === HISTORY_LIMIT);
      historyOffsetRef.current = reset ? data.length : off + data.length;
    } finally {
      setHistoryLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (tab === "queued" && historyItems.length === 0) loadHistory(true);
  }, [tab, historyItems.length, loadHistory]);

  // ── Article actions ────────────────────────────────────────────────────────
  function updateArticleLocally(id: string, updates: Partial<ArticleWithMeta>) {
    setArticles(prev => prev.map(a => a.id === id ? { ...a, ...updates } : a));
  }

  async function handleToggleStar(id: string, currently: boolean) {
    updateArticleLocally(id, { is_selected: !currently, ...(currently ? { tags: [] } : {}) });
    try {
      if (currently) await api.deselectArticle(id); else await api.selectArticle(id);
    } catch { updateArticleLocally(id, { is_selected: currently }); }
  }

  async function openPdf(article: ArticleWithMeta) {
    if (!article.pdf_on_server || pdfLoading) return;
    setPdfLoading(true);
    try {
      const blob = await api.downloadPdf(article.id);
      if (!blob || blob.size === 0) throw new Error("Empty PDF response");

      if (openPdfExternal) {
        const buf = await blob.arrayBuffer();
        const safeName = `${(article.title || article.id).slice(0, 60).replace(/[^a-zA-Z0-9._-]+/g, "_")}.pdf`;
        await openPdfExternal(new Uint8Array(buf), safeName);
        return;
      }

      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(URL.createObjectURL(blob));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("openPdf failed:", e);
      setArticleError(`Could not load PDF: ${msg}`);
    } finally { setPdfLoading(false); }
  }

  function closePdf() { if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl); setPdfBlobUrl(null); }

  function toggleEmailSelect(id: string) {
    setEmailSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  async function sendEmail() {
    if (!emailSelected.size) return;
    setEmailSending(true); setEmailStatus(null);
    try {
      const res = await api.emailArticles([...emailSelected]);
      setEmailStatus(`Sent to: ${res.sent_to.join(", ")}`);
      setEmailMode(false); setEmailSelected(new Set());
    } catch (err: unknown) {
      const e = err as ApiErrorType;
      setEmailStatus(e?.message ?? "Failed to send");
    } finally { setEmailSending(false); }
  }

  // ── History actions ────────────────────────────────────────────────────────
  const handleDeleteHistory = async (id: string) => {
    await api.deleteHistory(id);
    setHistoryItems(prev => prev.filter(i => i.id !== id));
  };

  const filteredHistory = historyItems.filter(i =>
    !historySearch ||
    i.title.toLowerCase().includes(historySearch.toLowerCase()) ||
    (i.journal ?? "").toLowerCase().includes(historySearch.toLowerCase()) ||
    i.authors.some(a => a.toLowerCase().includes(historySearch.toLowerCase()))
  );

  // ── Styles ─────────────────────────────────────────────────────────────────
  const S = {
    wrap:     { display: "flex", flexDirection: "column" as const, flex: 1, minHeight: 0, background: "var(--color-bg, #F5F0E8)" },
    header:   { display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.875rem 1.5rem", borderBottom: "1px solid var(--color-border, #D8D0C4)", background: "var(--color-bg-card, #FDFAF4)", flexShrink: 0, flexWrap: "wrap" as const },
    title:    { fontFamily: "'Playfair Display', Georgia, serif", fontSize: "1.1rem", color: "var(--color-text-primary, #1A2332)", margin: 0, flexShrink: 0 },
    search:   { flex: 1, minWidth: 120, padding: "0.4rem 0.75rem", border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.25rem", background: "var(--color-bg, #F5F0E8)", color: "var(--color-text-primary, #1A2332)", fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "0.875rem", outline: "none" },
    btn:      (active: boolean, variant?: "primary" | "ghost") => ({
      padding: "0.4rem 0.75rem", border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.25rem",
      background: variant === "primary" ? "var(--color-accent, #C0783A)" : active ? "var(--color-accent-light, #F0D4B4)" : "transparent",
      color: variant === "primary" ? "var(--color-bg-card, #FDFAF4)" : active ? "var(--color-accent-dim, #8A5228)" : "var(--color-text-secondary, #5A6475)",
      fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "0.8rem", fontWeight: 500,
      cursor: "pointer", flexShrink: 0, whiteSpace: "nowrap" as const,
    }),
    tabs:     { display: "flex", gap: 0, borderBottom: "1px solid var(--color-border, #D8D0C4)", padding: "0 1.5rem", background: "var(--color-bg-card, #FDFAF4)", flexShrink: 0 },
    tabItem:  (active: boolean) => ({
      padding: "0.625rem 1.25rem", fontFamily: "'DM Sans', system-ui, sans-serif", fontWeight: active ? 600 : 400,
      fontSize: "0.825rem", cursor: "pointer", border: "none", background: "transparent",
      color: active ? "var(--color-accent, #C0783A)" : "var(--color-text-secondary, #5A6475)",
      borderBottom: active ? "2px solid var(--color-accent, #C0783A)" : "2px solid transparent",
      transition: "color 0.15s",
    }),
    main:     { flex: 1, overflowY: "auto" as const, padding: "1.25rem 1.5rem" },
    empty:    { color: "var(--color-text-secondary, #5A6475)", textAlign: "center" as const, marginTop: "3rem", fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "0.875rem" },
    count:    { fontSize: "0.75rem", color: "var(--color-text-secondary, #5A6475)", marginBottom: "0.875rem", fontFamily: "'DM Mono', monospace" },
    articleRow: { borderBottom: "1px solid var(--color-border-light, #EDE6DA)", padding: "0.875rem 0", cursor: "pointer" },
    articleTitle: { fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 600, fontSize: "0.9rem", color: "var(--color-text-primary, #1A2332)", lineHeight: 1.4 },
    articleMeta:  { fontSize: "0.75rem", color: "var(--color-text-secondary, #5A6475)", marginTop: "0.25rem", fontFamily: "'DM Sans', system-ui, sans-serif" },
    abstract: { marginTop: "0.625rem", fontSize: "0.825rem", lineHeight: 1.65, color: "var(--color-text-primary, #1A2332)", fontFamily: "'Lora', Georgia, serif", background: "var(--color-bg, #F5F0E8)", borderRadius: "0.375rem", padding: "0.875rem", borderLeft: "3px solid var(--color-accent-light, #F0D4B4)" },
    pdfBadge: { fontSize: "0.65rem", background: "var(--color-accent-light, #F0D4B4)", color: "var(--color-accent-dim, #8A5228)", borderRadius: "0.2rem", padding: "0.15rem 0.4rem", fontFamily: "'DM Sans', system-ui, sans-serif", fontWeight: 600 },
    tag:      { fontSize: "0.65rem", background: "var(--color-bg, #F5F0E8)", color: "var(--color-text-secondary, #5A6475)", border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.2rem", padding: "0.1rem 0.375rem", fontFamily: "'DM Sans', system-ui, sans-serif" },
    starBtn:  (starred: boolean) => ({ background: "none", border: "none", cursor: "pointer", fontSize: "0.9rem", color: starred ? "var(--color-accent, #C0783A)" : "var(--color-border, #D8D0C4)", padding: "0.1rem 0.2rem" }),
    delBtn:   { background: "none", border: "none", cursor: "pointer", color: "var(--color-text-secondary, #5A6475)", fontSize: "0.75rem", padding: "0.125rem 0.25rem", opacity: 0.6 },
    loadMore: { marginTop: "1.25rem", padding: "0.5rem 1.25rem", border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.25rem", background: "transparent", cursor: "pointer", fontFamily: "'DM Sans', system-ui, sans-serif", fontWeight: 500, fontSize: "0.875rem", color: "var(--color-accent, #C0783A)" },
    statusBanner: { padding: "0.5rem 1.5rem", background: "var(--color-accent-light, #F0D4B4)", color: "var(--color-accent-dim, #8A5228)", fontSize: "0.8rem", fontFamily: "'DM Sans', system-ui, sans-serif", flexShrink: 0 },
  };

  const fmtDate = (s: string | null | undefined) =>
    s ? new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";

  return (
    <div style={S.wrap}>
      {/* PDF fullscreen overlay */}
      {pdfBlobUrl && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, background: "#000", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "flex-end", padding: "0.5rem", background: "var(--color-bg-dark, #1A2332)" }}>
            <button onClick={closePdf} style={{ ...S.btn(false, "primary"), fontSize: "0.875rem" }}>Close</button>
          </div>
          <iframe src={pdfBlobUrl} style={{ flex: 1, border: "none" }} title="Article PDF" />
        </div>
      )}

      {/* Header toolbar */}
      <header style={S.header}>
        <h1 style={S.title}>Library</h1>
        {tab === "downloaded" && (
          <input type="search" value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search articles…" style={S.search} />
        )}
        {tab === "downloaded" && (
          <button onClick={() => setSelectedOnly(v => !v)} style={S.btn(selectedOnly)}>
            ★ Starred
          </button>
        )}
        {tab === "downloaded" && !emailMode && (
          <button onClick={() => setEmailMode(true)} style={S.btn(false)}>✉ Email</button>
        )}
        {tab === "downloaded" && emailMode && (
          <>
            <button onClick={sendEmail} disabled={!emailSelected.size || emailSending} style={{ ...S.btn(false, "primary"), opacity: !emailSelected.size || emailSending ? 0.5 : 1 }}>
              {emailSending ? "Sending…" : `Send (${emailSelected.size})`}
            </button>
            <button onClick={() => { setEmailMode(false); setEmailSelected(new Set()); setEmailStatus(null); }} style={S.btn(false)}>
              Cancel
            </button>
          </>
        )}
        {onAddArticle && (
          <button onClick={onAddArticle} style={S.btn(false, "primary")}>+ Add article</button>
        )}
      </header>

      {emailStatus && <div style={S.statusBanner}>{emailStatus}</div>}

      {/* Tabs */}
      <div style={S.tabs}>
        <button style={S.tabItem(tab === "downloaded")} onClick={() => setTab("downloaded")}>
          Downloaded {total > 0 ? `(${total})` : ""}
        </button>
        <button style={S.tabItem(tab === "queued")} onClick={() => setTab("queued")}>
          Queued
        </button>
      </div>

      {/* Content */}
      <main style={S.main}>

        {/* ── Downloaded tab ── */}
        {tab === "downloaded" && (
          <>
            {pdfLoading && <p style={S.empty}>Loading PDF…</p>}
            {loadingArticles && <p style={S.empty}>Loading…</p>}
            {articleError && <p style={{ ...S.empty, color: "var(--color-error, #9B2C2C)" }}>{articleError}</p>}
            {!loadingArticles && !articleError && articles.length === 0 && (
              <p style={S.empty}>{debouncedQuery || selectedOnly ? "No articles match." : "No downloaded articles yet."}</p>
            )}
            {!loadingArticles && !articleError && articles.length > 0 && (
              <>
                <p style={S.count}>{total} article{total !== 1 ? "s" : ""}</p>
                {articles.map(a => (
                  <div key={a.id} style={S.articleRow}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                      {emailMode && (
                        <input type="checkbox" checked={emailSelected.has(a.id)}
                          onChange={() => toggleEmailSelect(a.id)}
                          style={{ marginTop: "0.25rem", flexShrink: 0, accentColor: "var(--color-accent, #C0783A)" }} />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={S.articleTitle} onClick={() => setExpandedArticle(expandedArticle === a.id ? null : a.id)}>
                          {a.title}
                        </div>
                        <div style={S.articleMeta}>
                          {a.authors.slice(0, 3).join(", ")}{a.authors.length > 3 ? " et al." : ""}
                          {a.journal && <span style={{ marginLeft: "0.5rem" }}>· {a.journal}</span>}
                          {a.year && <span style={{ marginLeft: "0.5rem", opacity: 0.7 }}>· {a.year}</span>}
                        </div>
                        {a.tags.length > 0 && (
                          <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginTop: "0.3rem" }}>
                            {a.tags.map(t => <span key={t} style={S.tag}>{t}</span>)}
                          </div>
                        )}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexShrink: 0 }}>
                        {a.pdf_on_server && (
                          <button onClick={() => openPdf(a)} style={{ ...S.pdfBadge, cursor: "pointer", border: "none", background: "var(--color-accent-light, #F0D4B4)" }} title="Open PDF">
                            PDF
                          </button>
                        )}
                        <button onClick={() => handleToggleStar(a.id, a.is_selected)} style={S.starBtn(a.is_selected)} title={a.is_selected ? "Unstar" : "Star"}>
                          {a.is_selected ? "★" : "☆"}
                        </button>
                      </div>
                    </div>
                    {expandedArticle === a.id && a.abstract && (
                      <div style={S.abstract}>{a.abstract}</div>
                    )}
                    {expandedArticle === a.id && !a.abstract && (
                      <div style={{ ...S.abstract, fontStyle: "italic", opacity: 0.6 }}>No abstract available.</div>
                    )}
                  </div>
                ))}
              </>
            )}
          </>
        )}

        {/* ── Queued tab ── */}
        {tab === "queued" && (
          <>
            <input value={historySearch} onChange={e => setHistorySearch(e.target.value)}
              placeholder="Search queued articles…"
              style={{ ...S.search, display: "block", marginBottom: "1.25rem", width: "100%", boxSizing: "border-box" as const }} />

            {historyLoading && historyItems.length === 0 && <p style={S.empty}>Loading…</p>}
            {!historyLoading && filteredHistory.length === 0 && (
              <p style={S.empty}>No queued articles yet. Download articles from the Journals page.</p>
            )}

            {filteredHistory.map(item => (
              <div key={item.id} style={S.articleRow}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={S.articleTitle} onClick={() => setExpandedHistory(expandedHistory === item.id ? null : item.id)}>
                      {item.title}
                    </div>
                    <div style={S.articleMeta}>
                      {item.authors.slice(0, 3).join(", ")}{item.authors.length > 3 ? " et al." : ""}
                      {item.journal && <span style={{ marginLeft: "0.5rem" }}>· {item.journal}</span>}
                      {item.pub_date && <span style={{ marginLeft: "0.5rem", opacity: 0.7 }}>· {item.pub_date}</span>}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.2rem", flexShrink: 0 }}>
                    <span style={{ fontFamily: "'DM Mono', monospace", fontSize: "0.68rem", color: "var(--color-text-secondary, #5A6475)" }}>
                      {fmtDate(item.queued_at)}
                    </span>
                    <button onClick={() => handleDeleteHistory(item.id)} style={S.delBtn} title="Remove">✕</button>
                  </div>
                </div>
                {expandedHistory === item.id && item.abstract && <div style={S.abstract}>{item.abstract}</div>}
                {expandedHistory === item.id && !item.abstract && <div style={{ ...S.abstract, fontStyle: "italic", opacity: 0.6 }}>No abstract available.</div>}
              </div>
            ))}

            {hasMoreHistory && !historyLoading && (
              <button onClick={() => loadHistory(false)} style={S.loadMore}>Load more</button>
            )}
            {historyLoading && historyItems.length > 0 && <p style={{ ...S.empty, marginTop: "1rem" }}>Loading…</p>}
          </>
        )}
      </main>
    </div>
  );
}
