import { useState, useRef, useEffect } from "react";
import type { ArticleWithMeta } from "@jc/shared";

interface Props {
  article: ArticleWithMeta;
  onOpen: (article: ArticleWithMeta) => void;
  onToggleStar: (id: string, currentlyStarred: boolean) => void;
  onTagsChange: (id: string, tags: string[]) => void;
  emailMode?: boolean;
  emailSelected?: boolean;
  onEmailToggle?: (id: string) => void;
  allTags?: string[];
}

const s = {
  card: {
    display: "flex",
    alignItems: "flex-start",
    gap: "0.625rem",
    background: "var(--color-surface-container-lowest)",
    border: "1px solid var(--color-outline-variant)",
    borderRadius: "var(--radius-lg)",
    padding: "0.875rem 1rem",
  } as React.CSSProperties,
  title: {
    margin: 0,
    fontFamily: "var(--font-headline)",
    fontSize: "0.9375rem",
    color: "var(--color-on-surface)",
    lineHeight: 1.4,
    cursor: "pointer",
  } as React.CSSProperties,
  meta: {
    margin: "0.2rem 0 0",
    fontSize: "0.775rem",
    color: "var(--color-on-surface-variant)",
    whiteSpace: "nowrap" as const,
    overflow: "hidden" as const,
    textOverflow: "ellipsis" as const,
  },
  tagChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.2rem",
    fontSize: "0.68rem",
    background: "var(--color-surface-container-high)",
    color: "var(--color-on-surface-variant)",
    padding: "0.15rem 0.4rem",
    borderRadius: "var(--radius)",
    fontFamily: "var(--font-label)",
  } as React.CSSProperties,
  iconBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0.1rem 0.2rem",
    lineHeight: 1,
    fontSize: "0.65rem",
    color: "var(--color-on-surface-variant)",
  } as React.CSSProperties,
  starBtn: (starred: boolean) => ({
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: "1.05rem",
    lineHeight: 1,
    padding: "0.1rem",
    color: starred ? "var(--color-secondary)" : "var(--color-outline)",
    flexShrink: 0,
  } as React.CSSProperties),
  addTagBtn: {
    background: "none",
    border: "1px dashed var(--color-outline-variant)",
    borderRadius: "var(--radius)",
    cursor: "pointer",
    padding: "0.1rem 0.35rem",
    fontSize: "0.68rem",
    color: "var(--color-on-surface-variant)",
    fontFamily: "var(--font-label)",
  } as React.CSSProperties,
  tagInput: {
    fontSize: "0.68rem",
    padding: "0.15rem 0.4rem",
    border: "1px solid var(--color-primary)",
    borderRadius: "var(--radius)",
    background: "var(--color-surface-container)",
    color: "var(--color-on-surface)",
    fontFamily: "var(--font-label)",
    outline: "none",
    width: 90,
  } as React.CSSProperties,
  dropdown: {
    position: "absolute" as const,
    top: "100%",
    left: 0,
    zIndex: 20,
    background: "var(--color-surface-container-lowest)",
    border: "1px solid var(--color-outline-variant)",
    borderRadius: "var(--radius)",
    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    minWidth: 120,
    display: "flex",
    flexDirection: "column" as const,
  },
  dropdownItem: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0.3rem 0.6rem",
    textAlign: "left" as const,
    fontSize: "0.75rem",
    fontFamily: "var(--font-label)",
    color: "var(--color-on-surface)",
  } as React.CSSProperties,
};

export function ArticleCard({
  article,
  onOpen,
  onToggleStar,
  onTagsChange,
  emailMode,
  emailSelected,
  onEmailToggle,
  allTags = [],
}: Props) {
  const [addingTag, setAddingTag] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (addingTag) inputRef.current?.focus();
  }, [addingTag]);

  const suggestions = tagInput.trim()
    ? allTags.filter(
        t => t.toLowerCase().includes(tagInput.toLowerCase()) && !article.tags.includes(t)
      ).slice(0, 5)
    : [];

  function addTag(tag: string) {
    const trimmed = tag.trim();
    setAddingTag(false);
    setTagInput("");
    if (!trimmed || article.tags.includes(trimmed)) return;
    onTagsChange(article.id, [...article.tags, trimmed]);
  }

  function removeTag(tag: string) {
    onTagsChange(article.id, article.tags.filter(t => t !== tag));
  }

  const authors =
    article.authors.length === 0 ? "" :
    article.authors.length <= 3 ? article.authors.join(", ") :
    `${article.authors[0]} et al.`;

  const metaParts = [authors, article.journal, article.year].filter(Boolean).join(" · ");

  return (
    <div style={s.card}>
      {emailMode && (
        <input
          type="checkbox"
          checked={emailSelected ?? false}
          onChange={() => onEmailToggle?.(article.id)}
          style={{ marginTop: "0.2rem", flexShrink: 0, cursor: "pointer", accentColor: "var(--color-primary)" }}
          disabled={!article.pdf_on_server}
        />
      )}

      {/* Star */}
      <button
        style={s.starBtn(article.is_selected)}
        onClick={() => onToggleStar(article.id, article.is_selected)}
        title={article.is_selected ? "Unstar" : "Star"}
      >
        {article.is_selected ? "★" : "☆"}
      </button>

      {/* Main content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={s.title}
          onClick={() => onOpen(article)}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--color-primary)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--color-on-surface)")}
        >
          {article.title}
        </p>
        {metaParts && <p style={s.meta}>{metaParts}</p>}

        {/* Tags row */}
        {(article.is_selected || article.tags.length > 0) && (
          <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.3rem", alignItems: "center" }}>
            {article.tags.map(tag => (
              <span key={tag} style={s.tagChip}>
                {tag}
                {article.is_selected && (
                  <button style={s.iconBtn} onClick={() => removeTag(tag)} title="Remove tag">×</button>
                )}
              </span>
            ))}
            {article.is_selected && !addingTag && (
              <button style={s.addTagBtn} onClick={() => setAddingTag(true)}>+ tag</button>
            )}
            {addingTag && (
              <div style={{ position: "relative" }}>
                <input
                  ref={inputRef}
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") { e.preventDefault(); addTag(tagInput); }
                    if (e.key === "Escape") { setAddingTag(false); setTagInput(""); }
                  }}
                  onBlur={() => setTimeout(() => { setAddingTag(false); setTagInput(""); }, 150)}
                  style={s.tagInput}
                  placeholder="tag name"
                />
                {suggestions.length > 0 && (
                  <div style={s.dropdown}>
                    {suggestions.map(sg => (
                      <button key={sg} style={s.dropdownItem} onMouseDown={() => addTag(sg)}>
                        {sg}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right: PDF badge */}
      {article.pdf_on_server && (
        <span style={{ fontSize: "0.65rem", background: "var(--color-primary-fixed)", color: "var(--color-primary)", padding: "0.2rem 0.45rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontWeight: 500, flexShrink: 0 }}>
          PDF
        </span>
      )}
    </div>
  );
}
