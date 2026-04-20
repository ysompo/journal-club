import React, { useState, useEffect, useCallback, useRef } from "react";
import type { JournalClubApi } from "../api";
import type { HistoryItem } from "../types";

interface Props {
  api: JournalClubApi;
}

export function HistoryPage({ api }: Props) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [hasMore, setHasMore] = useState(true);
  const offsetRef = useRef(0);
  const LIMIT = 50;

  const load = useCallback(async (reset = false) => {
    setLoading(true);
    const off = reset ? 0 : offsetRef.current;
    try {
      const data = await api.getHistory(LIMIT, off);
      setItems(prev => reset ? data : [...prev, ...data]);
      setHasMore(data.length === LIMIT);
      offsetRef.current = reset ? data.length : off + data.length;
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { load(true); }, [load]);

  const toggleExpand = (id: string) =>
    setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const handleDelete = async (id: string) => {
    await api.deleteHistory(id);
    setItems(prev => prev.filter(i => i.id !== id));
  };

  const filtered = items.filter(i =>
    !search ||
    i.title.toLowerCase().includes(search.toLowerCase()) ||
    (i.journal ?? "").toLowerCase().includes(search.toLowerCase()) ||
    i.authors.some(a => a.toLowerCase().includes(search.toLowerCase()))
  );

  const fmtDate = (s: string) => new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  return (
    <div style={{ padding: "1.5rem", maxWidth: 900, margin: "0 auto" }}>
      <h1 style={h1}>History</h1>
      <input
        value={search} onChange={e => setSearch(e.target.value)}
        placeholder="Search history…" style={searchStyle}
      />

      {filtered.length === 0 && !loading && (
        <div style={emptyStyle}>No articles in history yet. Queue articles from the Journals page.</div>
      )}

      {filtered.map(item => (
        <div key={item.id} style={rowStyle}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={titleStyle} onClick={() => toggleExpand(item.id)}>{item.title}</div>
              <div style={metaStyle}>
                {item.authors.slice(0, 3).join(", ")}{item.authors.length > 3 ? " et al." : ""}
                {item.journal && <span style={{ marginLeft: "0.5rem" }}>· {item.journal}</span>}
                {item.pub_date && <span style={{ marginLeft: "0.5rem", opacity: 0.7 }}>· {item.pub_date}</span>}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.25rem", flexShrink: 0 }}>
              <span style={{ fontSize: "0.7rem", color: "var(--color-on-surface-variant, #40484c)" }}>
                {fmtDate(item.queued_at)}
              </span>
              <button onClick={() => handleDelete(item.id)} style={deleteBtnStyle} title="Remove from history">✕</button>
            </div>
          </div>
          {expanded.has(item.id) && item.abstract && (
            <div style={abstractStyle}>{item.abstract}</div>
          )}
          {expanded.has(item.id) && !item.abstract && (
            <div style={{ ...abstractStyle, fontStyle: "italic", opacity: 0.7 }}>No abstract available.</div>
          )}
        </div>
      ))}

      {hasMore && !loading && (
        <button onClick={() => load(false)} style={loadMoreStyle}>Load more</button>
      )}
      {loading && <div style={emptyStyle}>Loading…</div>}
    </div>
  );
}

const h1: React.CSSProperties = { fontFamily: "'Noto Serif', serif", fontWeight: 700, fontSize: "1.5rem", marginBottom: "1rem", color: "var(--color-on-surface, #1a1c1e)" };
const searchStyle: React.CSSProperties = { width: "100%", padding: "0.5rem 0.75rem", borderRadius: "0.25rem", border: "1px solid var(--color-outline-variant, #d0d5d8)", fontFamily: "Inter, sans-serif", fontSize: "0.875rem", background: "var(--color-surface, #fff)", color: "var(--color-on-surface, #1a1c1e)", marginBottom: "1rem", boxSizing: "border-box" };
const rowStyle: React.CSSProperties = { borderBottom: "1px solid var(--color-outline-variant, #d0d5d8)", padding: "0.75rem 0" };
const titleStyle: React.CSSProperties = { fontFamily: "'Noto Serif', serif", fontWeight: 600, fontSize: "0.9rem", color: "var(--color-on-surface, #1a1c1e)", cursor: "pointer", lineHeight: 1.4 };
const metaStyle: React.CSSProperties = { fontSize: "0.775rem", color: "var(--color-on-surface-variant, #40484c)", marginTop: "0.2rem", fontFamily: "Inter, sans-serif" };
const abstractStyle: React.CSSProperties = { marginTop: "0.6rem", fontSize: "0.825rem", lineHeight: 1.6, color: "var(--color-on-surface, #1a1c1e)", fontFamily: "Inter, sans-serif", background: "var(--color-surface-container-low, #f0f4f5)", borderRadius: "0.25rem", padding: "0.75rem" };
const emptyStyle: React.CSSProperties = { color: "var(--color-on-surface-variant, #40484c)", fontSize: "0.875rem", fontFamily: "Inter, sans-serif", padding: "2rem 0", textAlign: "center" };
const deleteBtnStyle: React.CSSProperties = { background: "none", border: "none", cursor: "pointer", color: "var(--color-on-surface-variant, #40484c)", fontSize: "0.75rem", padding: "0.125rem 0.25rem" };
const loadMoreStyle: React.CSSProperties = { marginTop: "1rem", padding: "0.5rem 1.25rem", border: "1px solid var(--color-outline-variant, #d0d5d8)", borderRadius: "0.25rem", background: "transparent", cursor: "pointer", fontFamily: "'Work Sans', sans-serif", fontWeight: 500, fontSize: "0.875rem", color: "var(--color-primary, #005977)" };
