import { useState, type FormEvent, type CSSProperties } from "react";
import type { JournalClubApi } from "../api";

interface Props {
  api: JournalClubApi;
}

const wrap: CSSProperties = {
  padding: "2rem 2.5rem",
  maxWidth: 760,
  margin: "0 auto",
  fontFamily: "var(--font-body, system-ui)",
  color: "var(--color-on-surface)",
};
const h1: CSSProperties = {
  fontFamily: "var(--font-headline, Georgia)",
  fontSize: "1.6rem",
  margin: "0 0 0.4rem",
};
const sub: CSSProperties = {
  fontSize: "0.9rem",
  color: "var(--color-on-surface-variant)",
  margin: "0 0 1.75rem",
  lineHeight: 1.5,
};
const label: CSSProperties = {
  display: "block",
  fontSize: "0.78rem",
  fontFamily: "var(--font-label, system-ui)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--color-on-surface-variant)",
  marginBottom: "0.4rem",
};
const inp: CSSProperties = {
  width: "100%",
  padding: "0.65rem 0.85rem",
  border: "1px solid var(--color-outline-variant, #ccc)",
  borderRadius: "var(--radius, 6px)",
  background: "var(--color-surface-container, #fff)",
  color: "var(--color-on-surface)",
  fontFamily: "var(--font-body, system-ui)",
  fontSize: "0.95rem",
  outline: "none",
  boxSizing: "border-box",
};
const btn = (disabled: boolean): CSSProperties => ({
  padding: "0.6rem 1.4rem",
  background: disabled ? "var(--color-surface-container, #ddd)" : "var(--color-primary, #1A2332)",
  color: disabled ? "var(--color-on-surface-variant, #888)" : "var(--color-on-primary, #fff)",
  border: "none",
  borderRadius: "var(--radius, 6px)",
  fontFamily: "var(--font-label, system-ui)",
  fontSize: "0.9rem",
  fontWeight: 500,
  cursor: disabled ? "not-allowed" : "pointer",
});
const hintStyle = (kind: "info" | "error"): CSSProperties => ({
  marginTop: "1rem",
  padding: "0.75rem 1rem",
  borderRadius: "var(--radius, 6px)",
  background: kind === "error" ? "rgba(220,38,38,0.08)" : "rgba(34,197,94,0.08)",
  color: kind === "error" ? "rgba(180,30,30,1)" : "rgba(20,120,60,1)",
  fontSize: "0.875rem",
});

interface Hint { msg: string; kind: "info" | "error" }

export function ArticlesPage({ api }: Props) {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [hint, setHint] = useState<Hint | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const value = input.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    setHint(null);
    try {
      await api.enqueue(value);
      setHint({
        msg: "Queued. Watch the download panel at the bottom of the screen — the article will appear in your Library when it's done.",
        kind: "info",
      });
      setInput("");
    } catch (err) {
      const m = err instanceof Error ? err.message : String(err);
      setHint({ msg: `Could not queue: ${m}`, kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={wrap}>
      <h1 style={h1}>Articles</h1>
      <p style={sub}>
        Fetch a single article by DOI, PubMed ID, or ScienceDirect URL.
        Downloaded articles appear in your Library, and any bookmarks you add show in Bookmarks.
      </p>

      <form onSubmit={handleSubmit}>
        <label style={label} htmlFor="article-input">DOI, PubMed ID, or URL</label>
        <input
          id="article-input"
          autoFocus
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="10.1056/NEJMoa2504068   or   39794646   or   https://www.sciencedirect.com/science/article/pii/..."
          style={inp}
          disabled={submitting}
        />

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
          <button type="submit" disabled={!input.trim() || submitting} style={btn(!input.trim() || submitting)}>
            {submitting ? "Queueing…" : "Fetch"}
          </button>
        </div>
      </form>

      {hint && <div style={hintStyle(hint.kind)}>{hint.msg}</div>}

      <div style={{
        marginTop: "2.5rem",
        padding: "1rem 1.25rem",
        background: "var(--color-surface-container, #fafafa)",
        borderRadius: "var(--radius, 6px)",
        fontSize: "0.83rem",
        color: "var(--color-on-surface-variant)",
        lineHeight: 1.55,
      }}>
        <strong style={{ display: "block", marginBottom: "0.35rem", color: "var(--color-on-surface)" }}>
          Accepted formats
        </strong>
        <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
          <li>DOI — e.g. <code>10.1016/j.ajog.2025.12.010</code></li>
          <li>PubMed ID — bare number or <code>pmid:NNNNN</code></li>
          <li>PubMed URL — <code>https://pubmed.ncbi.nlm.nih.gov/NNNNN/</code></li>
          <li>Publisher article URL (ScienceDirect, NEJM, JAMA, etc.)</li>
        </ul>
      </div>
    </div>
  );
}
