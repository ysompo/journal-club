import { useState, useEffect, useCallback } from "react";
import { api, ApiError } from "@jc/shared";
import type { ArticleWithMeta } from "@jc/shared";
import { ArticleCard } from "./ArticleCard";
import { AddArticleModal } from "./AddArticleModal";
import { PairTabletModal } from "./PairTabletModal";
import { SettingsModal } from "./SettingsModal";

interface Props {
  onSignOut: () => void;
  hujiEmail: string;
  hujiPassword: string;
  chromeProfile: string;
  chromePath: string;
  refreshKey?: number;
}

export function ArchiveScreen({ onSignOut, hujiEmail, hujiPassword, chromeProfile, chromePath, refreshKey }: Props) {
  const [articles, setArticles] = useState<ArticleWithMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allTags, setAllTags] = useState<string[]>([]);

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showPairModal, setShowPairModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // PDF viewer overlay
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Email mode
  const [emailMode, setEmailMode] = useState(false);
  const [emailSelected, setEmailSelected] = useState<Set<string>>(new Set());
  const [emailSending, setEmailSending] = useState(false);
  const [emailStatus, setEmailStatus] = useState<string | null>(null);

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
        onSignOut();
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to load articles");
      }
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, selectedOnly, onSignOut]);

  useEffect(() => { fetchArticles(); }, [fetchArticles, refreshKey]);

  useEffect(() => {
    api.getTags().then(setAllTags).catch(() => {});
  }, [articles]);

  // ── Star / tags ────────────────────────────────────────────────────────────

  function updateArticleLocally(id: string, updates: Partial<ArticleWithMeta>) {
    setArticles(prev => prev.map(a => a.id === id ? { ...a, ...updates } : a));
  }

  async function handleToggleStar(id: string, currentlyStarred: boolean) {
    updateArticleLocally(id, { is_selected: !currentlyStarred, ...(currentlyStarred ? { tags: [] } : {}) });
    try {
      if (currentlyStarred) {
        await api.deselectArticle(id);
      } else {
        await api.selectArticle(id);
      }
    } catch {
      updateArticleLocally(id, { is_selected: currentlyStarred });
    }
  }

  async function handleTagsChange(id: string, tags: string[]) {
    updateArticleLocally(id, { tags });
    try {
      await api.updateTags(id, tags);
    } catch {}
  }

  // ── PDF viewer ─────────────────────────────────────────────────────────────

  async function openPdf(article: ArticleWithMeta) {
    if (!article.pdf_on_server || pdfLoading) return;
    setPdfLoading(true);
    try {
      const blob = await api.downloadPdf(article.id);
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(URL.createObjectURL(blob));
    } catch {
      setError("Could not load PDF");
    } finally {
      setPdfLoading(false);
    }
  }

  function closePdf() {
    if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    setPdfBlobUrl(null);
  }

  // ── Email ──────────────────────────────────────────────────────────────────

  function toggleEmailSelect(id: string) {
    setEmailSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function sendEmail() {
    if (emailSelected.size === 0) return;
    setEmailSending(true);
    setEmailStatus(null);
    try {
      const res = await api.emailArticles([...emailSelected]);
      setEmailStatus(`Sent to: ${res.sent_to.join(", ")}`);
      setEmailMode(false);
      setEmailSelected(new Set());
    } catch (err) {
      setEmailStatus(err instanceof ApiError ? err.message : "Failed to send");
    } finally {
      setEmailSending(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, background: "var(--color-surface)" }}>
      {/* PDF overlay */}
      {pdfBlobUrl && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, background: "#000", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "flex-end", padding: "0.5rem", background: "var(--color-surface-container)" }}>
            <button onClick={closePdf} style={{ padding: "0.4rem 0.875rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", cursor: "pointer" }}>
              Close
            </button>
          </div>
          <iframe src={pdfBlobUrl} style={{ flex: 1, border: "none" }} title="Article PDF" />
        </div>
      )}

      {/* Top bar */}
      <header style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.75rem 1.5rem", borderBottom: "1px solid var(--color-outline-variant)", background: "var(--color-surface-container-lowest)", flexShrink: 0 }}>
        <h1 style={{ fontFamily: "var(--font-headline)", fontSize: "1.25rem", color: "var(--color-primary)", margin: 0, flexShrink: 0 }}>
          Journal Club
        </h1>

        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search articles…"
          style={{ flex: 1, padding: "0.4rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.9rem", outline: "none" }}
        />

        <button
          onClick={() => setSelectedOnly(v => !v)}
          style={{ padding: "0.4rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: selectedOnly ? "var(--color-primary)" : "var(--color-surface-container)", color: selectedOnly ? "var(--color-on-primary)" : "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer", flexShrink: 0 }}
        >
          ★ Favourites
        </button>

        {emailMode ? (
          <>
            <button
              onClick={sendEmail}
              disabled={emailSelected.size === 0 || emailSending}
              style={{ padding: "0.4rem 0.875rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500, cursor: "pointer", opacity: emailSelected.size === 0 || emailSending ? 0.5 : 1, flexShrink: 0 }}
            >
              {emailSending ? "Sending…" : `Send (${emailSelected.size})`}
            </button>
            <button
              onClick={() => { setEmailMode(false); setEmailSelected(new Set()); setEmailStatus(null); }}
              style={{ padding: "0.4rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer", flexShrink: 0 }}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => setEmailMode(true)}
              style={{ padding: "0.4rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer", flexShrink: 0 }}
            >
              ✉ Email
            </button>
            <button
              onClick={() => setShowPairModal(true)}
              style={{ padding: "0.4rem 0.875rem", background: "none", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer", color: "var(--color-on-surface-variant)", flexShrink: 0 }}
            >
              Pair tablet
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              style={{ padding: "0.4rem 0.875rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500, cursor: "pointer", flexShrink: 0 }}
            >
              + Add article
            </button>
            <button
              onClick={() => setShowSettings(true)}
              style={{ padding: "0.4rem 0.6rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.9rem", cursor: "pointer", flexShrink: 0 }}
              title="Settings"
            >
              ⚙
            </button>
            <button
              onClick={onSignOut}
              style={{ padding: "0.4rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.8rem", cursor: "pointer", flexShrink: 0 }}
            >
              Sign out
            </button>
          </>
        )}
      </header>

      {emailStatus && (
        <div style={{ padding: "0.5rem 1.5rem", background: "var(--color-primary-fixed)", color: "var(--color-primary)", fontSize: "0.8rem", fontFamily: "var(--font-body)", flexShrink: 0 }}>
          {emailStatus}
        </div>
      )}

      {/* Content */}
      <main style={{ flex: 1, overflowY: "auto", padding: "1rem 1.5rem" }}>
        {pdfLoading && (
          <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", marginTop: "1rem", fontSize: "0.85rem" }}>
            Loading PDF…
          </p>
        )}
        {loading && (
          <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", marginTop: "3rem" }}>Loading…</p>
        )}
        {error && (
          <p style={{ color: "var(--color-error)", textAlign: "center", marginTop: "3rem" }}>{error}</p>
        )}
        {!loading && !error && articles.length === 0 && (
          <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", marginTop: "3rem" }}>
            {debouncedQuery || selectedOnly ? "No articles match your search." : "No articles yet. Add one with the button above."}
          </p>
        )}
        {!loading && !error && articles.length > 0 && (
          <>
            <p style={{ fontSize: "0.8rem", color: "var(--color-on-surface-variant)", marginBottom: "0.75rem" }}>
              {total} article{total !== 1 ? "s" : ""}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {articles.map(article => (
                <ArticleCard
                  key={article.id}
                  article={article}
                  onOpen={openPdf}
                  onToggleStar={handleToggleStar}
                  onTagsChange={handleTagsChange}
                  emailMode={emailMode}
                  emailSelected={emailSelected.has(article.id)}
                  onEmailToggle={toggleEmailSelect}
                  allTags={allTags}
                />
              ))}
            </div>
          </>
        )}
      </main>

      {showPairModal && (
        <PairTabletModal
          onClose={() => setShowPairModal(false)}
          pwaUrl={(import.meta.env.VITE_PWA_URL as string | undefined) ?? "http://localhost:3000"}
        />
      )}

      {showAddModal && (
        <AddArticleModal
          onClose={() => setShowAddModal(false)}
          onArticleAdded={() => { setShowAddModal(false); fetchArticles(); }}
          hujiEmail={hujiEmail}
          hujiPassword={hujiPassword}
          chromeProfile={chromeProfile}
          chromePath={chromePath}
        />
      )}

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
