import React, { useState, useEffect } from "react";
import type { JournalClubApi, ArticleWithMeta } from "../api";

interface Props {
  api: JournalClubApi;
}

export function BookmarksPage({ api }: Props) {
  const [articles, setArticles] = useState<ArticleWithMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.getArticles({ selected_only: true, limit: 200 })
      .then(r => setArticles(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api]);

  const toggleExpand = (id: string) =>
    setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const handleUnbookmark = async (article: ArticleWithMeta) => {
    await api.deselectArticle(article.id);
    setArticles(prev => prev.filter(a => a.id !== article.id));
  };

  const filtered = articles.filter(a =>
    !search ||
    a.title.toLowerCase().includes(search.toLowerCase()) ||
    (a.journal ?? "").toLowerCase().includes(search.toLowerCase()) ||
    a.authors.some(au => au.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div style={{ padding: "1.75rem 2rem", maxWidth: 900, margin: "0 auto" }}>
      <h1 style={h1}>Bookmarks</h1>

      <input
        value={search} onChange={e => setSearch(e.target.value)}
        placeholder="Search bookmarks…" style={searchStyle}
      />

      {loading && <div style={emptyStyle}>Loading…</div>}
      {!loading && filtered.length === 0 && (
        <div style={emptyStyle}>No bookmarks yet. Star articles from the Library page.</div>
      )}

      {filtered.map(article => (
        <div key={article.id} style={rowStyle}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={titleStyle} onClick={() => toggleExpand(article.id)}>
                {article.title}
              </div>
              <div style={metaStyle}>
                {article.authors.slice(0, 3).join(", ")}{article.authors.length > 3 ? " et al." : ""}
                {article.journal && <span style={{ marginLeft: "0.5rem" }}>· {article.journal}</span>}
                {article.year && <span style={{ marginLeft: "0.5rem", fontFamily: "var(--font-mono, monospace)", opacity: 0.7 }}>· {article.year}</span>}
              </div>
              {article.tags.length > 0 && (
                <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", marginTop: "0.4rem" }}>
                  {article.tags.map(tag => (
                    <span key={tag} style={tagStyle}>{tag}</span>
                  ))}
                </div>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
              {article.pdf_on_server && (
                <span style={pdfBadge}>PDF</span>
              )}
              <button
                onClick={() => handleUnbookmark(article)}
                style={unbookmarkStyle}
                title="Remove bookmark"
              >
                ★ Remove
              </button>
            </div>
          </div>
          {expanded.has(article.id) && article.abstract && (
            <div style={abstractStyle}>{article.abstract}</div>
          )}
          {expanded.has(article.id) && !article.abstract && (
            <div style={{ ...abstractStyle, fontStyle: "italic", opacity: 0.7 }}>No abstract available.</div>
          )}
        </div>
      ))}
    </div>
  );
}

const h1: React.CSSProperties = {
  fontFamily: "var(--font-headline, 'Playfair Display', Georgia, serif)",
  fontWeight: 700, fontSize: "1.6rem", marginBottom: "1.25rem",
  color: "var(--color-text-primary, #1A2332)",
};
const searchStyle: React.CSSProperties = {
  width: "100%", padding: "0.5rem 0.75rem",
  borderRadius: "0.25rem",
  border: "1px solid var(--color-border, #D8D0C4)",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  fontSize: "0.875rem",
  background: "var(--color-bg-card, #FDFAF4)",
  color: "var(--color-text-primary, #1A2332)",
  marginBottom: "1rem", boxSizing: "border-box",
  outline: "none",
};
const rowStyle: React.CSSProperties = {
  borderBottom: "1px solid var(--color-border-light, #EDE6DA)",
  padding: "0.875rem 0",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--font-headline, 'Playfair Display', Georgia, serif)",
  fontWeight: 600, fontSize: "0.925rem",
  color: "var(--color-text-primary, #1A2332)",
  cursor: "pointer", lineHeight: 1.4,
};
const metaStyle: React.CSSProperties = {
  fontSize: "0.775rem",
  color: "var(--color-text-secondary, #5A6475)",
  marginTop: "0.25rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
};
const abstractStyle: React.CSSProperties = {
  marginTop: "0.75rem", fontSize: "0.825rem", lineHeight: 1.65,
  color: "var(--color-text-primary, #1A2332)",
  fontFamily: "var(--font-body, 'Lora', Georgia, serif)",
  background: "var(--color-bg, #F5F0E8)",
  borderRadius: "0.25rem", padding: "0.875rem 1rem",
  borderLeft: "3px solid var(--color-accent, #C0783A)",
};
const emptyStyle: React.CSSProperties = {
  color: "var(--color-text-secondary, #5A6475)",
  fontSize: "0.875rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  padding: "2.5rem 0", textAlign: "center",
};
const tagStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  background: "var(--color-accent-light, #F0D4B4)",
  color: "var(--color-accent-dim, #8A5228)",
  borderRadius: "0.2rem", padding: "0.15rem 0.4rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  fontWeight: 500,
};
const pdfBadge: React.CSSProperties = {
  fontSize: "0.7rem",
  background: "var(--color-accent-light, #F0D4B4)",
  color: "var(--color-accent-dim, #8A5228)",
  borderRadius: "0.2rem", padding: "0.15rem 0.4rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  fontWeight: 600,
};
const unbookmarkStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid var(--color-border, #D8D0C4)",
  borderRadius: "0.25rem", cursor: "pointer",
  color: "var(--color-accent, #C0783A)",
  fontSize: "0.75rem", padding: "0.25rem 0.5rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
};
