"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@jc/shared";
import type { ArticleWithMeta, QueueItem } from "@jc/shared";
import { loadToken, clearToken } from "../lib/auth";

const ONLINE_POLL_MS = 30_000;
const QUEUE_POLL_MS = 15_000;

export default function ArchivePage() {
  const router = useRouter();
  const [articles, setArticles] = useState<ArticleWithMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPdfUrl, setOpenPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Add article
  const [showAdd, setShowAdd] = useState(false);
  const [starBusy, setStarBusy] = useState<string | null>(null);
  const [addInput, setAddInput] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // PC online status
  const [pcOnline, setPcOnline] = useState<boolean | null>(null);

  // Queue items
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const prevQueueRef = useRef<QueueItem[]>([]);

  // Redirect if not authed
  useEffect(() => {
    if (!loadToken()) router.replace("/login");
  }, [router]);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getArticles({
        q: debouncedQuery || undefined,
        selected_only: selectedOnly || undefined,
        limit: 100,
      });
      setArticles(res.items);
      setTotal(res.total);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        router.replace("/login");
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to load");
      }
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, selectedOnly, router]);

  useEffect(() => { fetchArticles(); }, [fetchArticles]);

  // Poll PC online status
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await api.desktopOnlineStatus();
        if (!cancelled) setPcOnline(res.online);
      } catch {
        if (!cancelled) setPcOnline(false);
      }
    }
    check();
    const t = setInterval(check, ONLINE_POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  // Poll queue — refresh articles when a "done" item appears
  const fetchQueue = useCallback(async () => {
    try {
      const items = await api.getQueue();
      setQueueItems(items.filter(i => i.status !== "done"));
      // detect newly done items to trigger article list refresh
      const prev = prevQueueRef.current;
      const newDone = items.filter(i => i.status === "done" && !prev.find(p => p.id === i.id && p.status === "done"));
      if (newDone.length > 0) fetchArticles();
      prevQueueRef.current = items;
    } catch {}
  }, [fetchArticles]);

  useEffect(() => {
    fetchQueue();
    const t = setInterval(fetchQueue, QUEUE_POLL_MS);
    return () => clearInterval(t);
  }, [fetchQueue]);

  function signOut() {
    clearToken();
    router.push("/login");
  }

  async function openPdf(article: ArticleWithMeta) {
    if (!article.pdf_on_server || pdfLoading) return;
    setPdfLoading(true);
    try {
      const blob = await api.downloadPdf(article.id);
      const blobUrl = URL.createObjectURL(blob);
      setOpenPdfUrl(blobUrl);
    } catch {
      setError("Could not load PDF");
    } finally {
      setPdfLoading(false);
    }
  }

  function closePdf() {
    if (openPdfUrl) URL.revokeObjectURL(openPdfUrl);
    setOpenPdfUrl(null);
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const input = addInput.trim();
    if (!input) return;
    setAddLoading(true);
    setAddError(null);
    try {
      await api.enqueue(input);
      setAddInput("");
      setShowAdd(false);
      fetchQueue();
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : "Failed to add");
    } finally {
      setAddLoading(false);
    }
  }

  async function handleToggleStar(article: ArticleWithMeta) {
    if (starBusy) return;
    setStarBusy(article.id);
    const wasStarred = article.is_selected;
    setArticles(prev => prev.map(a => a.id === article.id ? { ...a, is_selected: !wasStarred, tags: wasStarred ? [] : a.tags } : a));
    try {
      if (wasStarred) await api.deselectArticle(article.id);
      else await api.selectArticle(article.id);
    } catch {
      setArticles(prev => prev.map(a => a.id === article.id ? { ...a, is_selected: wasStarred } : a));
    } finally {
      setStarBusy(null);
    }
  }

  async function handleRetry(id: string) {
    try {
      await api.retryQueueItem(id);
      fetchQueue();
    } catch {}
  }

  async function handleDeleteQueued(id: string) {
    try {
      await api.deleteQueueItem(id);
      setQueueItems(prev => prev.filter(i => i.id !== id));
    } catch {}
  }

  const activeQueue = queueItems.filter(i => i.status === "queued" || i.status === "claimed" || i.status === "downloading");
  const failedQueue = queueItems.filter(i => i.status === "failed");

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100dvh", background: "var(--color-surface)" }}>
      {/* Header */}
      <header style={{ position: "sticky", top: 0, zIndex: 10, background: "var(--color-surface-container-lowest)", borderBottom: "1px solid var(--color-outline-variant)", padding: "0.625rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <span style={{ fontFamily: "var(--font-headline)", fontSize: "1.1rem", color: "var(--color-primary)", flexShrink: 0 }}>
          Journal Club
        </span>

        {/* PC online badge */}
        {pcOnline !== null && (
          <span title={pcOnline ? "Desktop is online" : "Desktop is offline"} style={{
            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
            background: pcOnline ? "var(--color-primary)" : "var(--color-error)",
          }} />
        )}

        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search…"
          style={{ flex: 1, minWidth: 0, padding: "0.375rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.875rem", outline: "none" }}
        />
        <button
          onClick={() => setSelectedOnly(v => !v)}
          style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: selectedOnly ? "var(--color-primary)" : "var(--color-surface-container)", color: selectedOnly ? "var(--color-on-primary)" : "var(--color-on-surface-variant)", fontSize: "0.8rem", fontFamily: "var(--font-label)", cursor: "pointer", flexShrink: 0 }}
        >
          ★
        </button>
        <button
          onClick={() => { setShowAdd(true); setAddError(null); }}
          style={{ padding: "0.35rem 0.6rem", border: "none", borderRadius: "var(--radius)", background: "var(--color-primary)", color: "var(--color-on-primary)", fontSize: "0.8rem", fontFamily: "var(--font-label)", fontWeight: 500, cursor: "pointer", flexShrink: 0 }}
        >
          + Add
        </button>
        <button
          onClick={() => router.push("/settings")}
          style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontSize: "0.875rem", fontFamily: "var(--font-label)", cursor: "pointer", flexShrink: 0 }}
          title="Settings"
        >
          ⚙
        </button>
        <button
          onClick={signOut}
          style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontSize: "0.75rem", fontFamily: "var(--font-label)", cursor: "pointer", flexShrink: 0 }}
        >
          Out
        </button>
      </header>

      {/* Add article modal */}
      {showAdd && (
        <div style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <div style={{ background: "var(--color-surface-container-lowest)", borderRadius: "var(--radius-lg)", padding: "1.5rem", width: "100%", maxWidth: 420 }}>
            <h2 style={{ margin: "0 0 1rem", fontFamily: "var(--font-headline)", fontSize: "1.125rem", color: "var(--color-on-surface)" }}>
              Add article
            </h2>
            <p style={{ margin: "0 0 1rem", fontSize: "0.8rem", color: "var(--color-on-surface-variant)" }}>
              Enter a PMID, DOI, or URL. The desktop app will download it when online.
            </p>
            <form onSubmit={handleAdd} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <input
                autoFocus
                type="text"
                value={addInput}
                onChange={e => setAddInput(e.target.value)}
                placeholder="e.g. 39281234 or 10.1016/j.ajog.2024… or https://…"
                style={{ padding: "0.5rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.875rem", outline: "none" }}
              />
              {addError && (
                <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-error)" }}>{addError}</p>
              )}
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                <button type="button" onClick={() => setShowAdd(false)} style={{ padding: "0.4rem 0.875rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer" }}>
                  Cancel
                </button>
                <button type="submit" disabled={addLoading || !addInput.trim()} style={{ padding: "0.4rem 0.875rem", border: "none", borderRadius: "var(--radius)", background: "var(--color-primary)", color: "var(--color-on-primary)", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500, cursor: "pointer", opacity: addLoading || !addInput.trim() ? 0.5 : 1 }}>
                  {addLoading ? "Adding…" : "Add"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* PDF viewer overlay */}
      {openPdfUrl && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, background: "#000", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "flex-end", padding: "0.5rem", background: "var(--color-surface-container)" }}>
            <button onClick={closePdf} style={{ padding: "0.35rem 0.75rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", cursor: "pointer" }}>
              Close
            </button>
          </div>
          <iframe src={openPdfUrl} style={{ flex: 1, border: "none" }} title="Article PDF" />
        </div>
      )}

      {/* Queue status */}
      {(activeQueue.length > 0 || failedQueue.length > 0) && (
        <div style={{ borderBottom: "1px solid var(--color-outline-variant)", background: "var(--color-surface-container-lowest)", padding: "0.5rem 1rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          {activeQueue.map(item => (
            <div key={item.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem" }}>
              <span style={{ flex: 1, minWidth: 0, color: "var(--color-on-surface-variant)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                ⏳ {item.input.length > 55 ? item.input.slice(0, 55) + "…" : item.input}
              </span>
              <span style={{ flexShrink: 0, fontSize: "0.65rem", background: "var(--color-surface-container-high)", color: "var(--color-on-surface-variant)", padding: "0.1rem 0.35rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)" }}>
                {item.status}
              </span>
              <button onClick={() => handleDeleteQueued(item.id)} style={{ flexShrink: 0, fontSize: "0.65rem", padding: "0.1rem 0.35rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", cursor: "pointer", fontFamily: "var(--font-label)" }}>
                ✕
              </button>
            </div>
          ))}
          {failedQueue.map(item => (
            <div key={item.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem" }}>
              <span style={{ flex: 1, minWidth: 0, color: "var(--color-error)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.error ?? ""}>
                ✗ {item.input.length > 45 ? item.input.slice(0, 45) + "…" : item.input}
                {item.error && <span style={{ color: "var(--color-on-surface-variant)" }}> — {item.error.slice(0, 40)}</span>}
              </span>
              <span style={{ flexShrink: 0, fontSize: "0.65rem", background: "var(--color-error-container)", color: "var(--color-error)", padding: "0.1rem 0.35rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)" }}>
                failed {item.retry_count}×
              </span>
              <button onClick={() => handleRetry(item.id)} style={{ flexShrink: 0, fontSize: "0.65rem", padding: "0.1rem 0.35rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", cursor: "pointer", fontFamily: "var(--font-label)" }}>
                Retry
              </button>
              <button onClick={() => handleDeleteQueued(item.id)} style={{ flexShrink: 0, fontSize: "0.65rem", padding: "0.1rem 0.35rem", border: "1px solid var(--color-error)", borderRadius: "var(--radius)", background: "none", color: "var(--color-error)", cursor: "pointer", fontFamily: "var(--font-label)" }}>
                Delete
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      <main style={{ flex: 1, padding: "0.875rem 1rem" }}>
        {loading && (
          <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", marginTop: "3rem", fontSize: "0.875rem" }}>Loading…</p>
        )}
        {error && (
          <p style={{ color: "var(--color-error)", textAlign: "center", marginTop: "3rem", fontSize: "0.875rem" }}>{error}</p>
        )}
        {!loading && !error && articles.length === 0 && (
          <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", marginTop: "3rem", fontSize: "0.875rem" }}>
            {debouncedQuery || selectedOnly ? "No articles match." : "No articles yet. Tap + Add to request one."}
          </p>
        )}
        {!loading && !error && articles.length > 0 && (
          <>
            <p style={{ fontSize: "0.75rem", color: "var(--color-on-surface-variant)", marginBottom: "0.625rem" }}>
              {total} article{total !== 1 ? "s" : ""}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {articles.map(article => (
                <ArticleRow key={article.id} article={article} onOpen={openPdf} pdfLoading={pdfLoading} onToggleStar={handleToggleStar} starBusy={starBusy === article.id} />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function ArticleRow({ article, onOpen, pdfLoading, onToggleStar, starBusy }: { article: ArticleWithMeta; onOpen: (a: ArticleWithMeta) => void; pdfLoading: boolean; onToggleStar: (a: ArticleWithMeta) => void; starBusy: boolean }) {
  const authors =
    article.authors.length === 0 ? "" :
    article.authors.length <= 2 ? article.authors.join(", ") :
    `${article.authors[0]} et al.`;

  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "0.875rem 1rem" }}>
      {/* Star */}
      <button
        onClick={() => onToggleStar(article)}
        disabled={starBusy}
        style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.1rem", color: article.is_selected ? "var(--color-secondary)" : "var(--color-outline)", padding: "0", flexShrink: 0, lineHeight: 1, marginTop: "0.1rem", opacity: starBusy ? 0.5 : 1 }}
      >
        {article.is_selected ? "★" : "☆"}
      </button>

      {/* Content */}
      <button
        onClick={() => article.pdf_on_server && onOpen(article)}
        style={{ flex: 1, minWidth: 0, textAlign: "left", background: "none", border: "none", padding: 0, cursor: article.pdf_on_server ? "pointer" : "default" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
          <p style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "0.9375rem", color: "var(--color-on-surface)", lineHeight: 1.4 }}>
            {article.title}
          </p>
          {article.pdf_on_server && (
            <span style={{ fontSize: "0.65rem", background: "var(--color-primary-fixed)", color: "var(--color-primary)", padding: "0.15rem 0.4rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontWeight: 500, flexShrink: 0 }}>
              {pdfLoading ? "…" : "PDF"}
            </span>
          )}
        </div>
        {(authors || article.journal || article.year) && (
          <p style={{ margin: "0.3rem 0 0", fontSize: "0.75rem", color: "var(--color-on-surface-variant)", textAlign: "left" }}>
            {[authors, article.journal, article.year].filter(Boolean).join(" · ")}
          </p>
        )}
        {article.tags.length > 0 && (
          <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
            {article.tags.map(tag => (
              <span key={tag} style={{ fontSize: "0.65rem", background: "var(--color-surface-container)", color: "var(--color-on-surface-variant)", padding: "0.1rem 0.4rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)" }}>
                {tag}
              </span>
            ))}
          </div>
        )}
      </button>
    </div>
  );
}
