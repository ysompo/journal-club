import React, { useState } from "react";
import type { TocArticle } from "../types";

export type DownloadStatus = "idle" | "queued" | "downloading" | "done" | "failed";

interface Props {
  article: TocArticle;
  downloadStatus: DownloadStatus;
  queuePosition?: number;   // 1-based position in queue if status=queued
  isBookmarked: boolean;
  onDownload: () => void;
  onCancelDownload: () => void;
  onBookmark: () => void;
  onEmail?: () => void;
  onReport?: () => void;
}

function truncateAuthors(authors: string[], max = 3): string {
  if (authors.length <= max) return authors.join(", ");
  return authors.slice(0, max).join(", ") + " et al.";
}

export function ArticleRow({
  article,
  downloadStatus,
  queuePosition,
  isBookmarked,
  onDownload,
  onCancelDownload,
  onBookmark,
  onEmail,
  onReport,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const downloadLabel = () => {
    if (downloadStatus === "queued" && queuePosition != null && queuePosition > 1)
      return `#${queuePosition}`;
    if (downloadStatus === "queued") return "Queued";
    if (downloadStatus === "downloading") return "Downloading…";
    if (downloadStatus === "done") return "✓ Done";
    if (downloadStatus === "failed") return "Failed";
    return "Download";
  };

  const downloadColor = () => {
    if (downloadStatus === "queued") return "var(--color-secondary, #9f4200)";
    if (downloadStatus === "downloading") return "var(--color-primary, #005977)";
    if (downloadStatus === "done") return "#2e7d32";
    if (downloadStatus === "failed") return "var(--color-error, #ba1a1a)";
    return "var(--color-primary, #005977)";
  };

  const canCancel = downloadStatus === "idle" || downloadStatus === "queued";

  return (
    <div style={{
      borderBottom: "1px solid var(--color-outline-variant, #d0d5d8)",
      padding: "0.75rem 0",
    }}>
      {/* Title row */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: "'Noto Serif', serif",
              fontWeight: 600,
              fontSize: "0.9rem",
              color: "var(--color-on-surface, #1a1c1e)",
              cursor: "pointer",
              lineHeight: 1.4,
            }}
            onClick={() => setExpanded(e => !e)}
          >
            {article.title}
          </div>
          <div style={{
            fontSize: "0.775rem",
            color: "var(--color-on-surface-variant, #40484c)",
            marginTop: "0.2rem",
            fontFamily: "Inter, sans-serif",
          }}>
            {truncateAuthors(article.authors)}
            {article.pub_date && (
              <span style={{ marginLeft: "0.5rem", opacity: 0.7 }}>· {article.pub_date}</span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexShrink: 0 }}>
          {onEmail && (
            <button
              title="Add to email list"
              onClick={onEmail}
              style={btnStyle("var(--color-on-surface-variant, #40484c)")}
            >
              📧
            </button>
          )}
          <button
            title={isBookmarked ? "Remove bookmark" : "Bookmark"}
            onClick={onBookmark}
            style={btnStyle(isBookmarked ? "var(--color-secondary, #9f4200)" : "var(--color-on-surface-variant, #40484c)")}
          >
            {isBookmarked ? "🔖" : "🔖"}
          </button>
          {downloadStatus === "failed" && onReport && (
            <button
              onClick={onReport}
              style={{
                ...btnStyle("var(--color-error, #ba1a1a)"),
                fontSize: "0.7rem",
                padding: "0.25rem 0.5rem",
              }}
            >
              Report
            </button>
          )}
          <button
            onClick={canCancel ? (downloadStatus === "idle" ? onDownload : onCancelDownload) : undefined}
            disabled={downloadStatus === "downloading" || downloadStatus === "done"}
            style={{
              padding: "0.3rem 0.65rem",
              borderRadius: "0.25rem",
              border: `1px solid ${downloadColor()}`,
              background: downloadStatus === "done" ? "#e8f5e9" : downloadStatus === "failed" ? "#fdecea" : "transparent",
              color: downloadColor(),
              cursor: (downloadStatus === "downloading" || downloadStatus === "done") ? "default" : "pointer",
              fontSize: "0.775rem",
              fontFamily: "'Work Sans', sans-serif",
              fontWeight: 500,
              minWidth: 72,
              textAlign: "center",
              opacity: (downloadStatus === "downloading" || downloadStatus === "done") ? 0.8 : 1,
              transition: "all 0.12s",
            }}
          >
            {downloadLabel()}
          </button>
        </div>
      </div>

      {/* Abstract (expanded) */}
      {expanded && article.abstract && (
        <div style={{
          marginTop: "0.6rem",
          fontSize: "0.825rem",
          lineHeight: 1.6,
          color: "var(--color-on-surface, #1a1c1e)",
          fontFamily: "Inter, sans-serif",
          background: "var(--color-surface-container-low, #f0f4f5)",
          borderRadius: "0.25rem",
          padding: "0.75rem",
        }}>
          {article.abstract}
        </div>
      )}
      {expanded && !article.abstract && (
        <div style={{
          marginTop: "0.6rem",
          fontSize: "0.8rem",
          color: "var(--color-on-surface-variant, #40484c)",
          fontStyle: "italic",
        }}>
          No abstract available.
        </div>
      )}
    </div>
  );
}

function btnStyle(color: string): React.CSSProperties {
  return {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0.25rem",
    borderRadius: "0.25rem",
    color,
    fontSize: "1rem",
    lineHeight: 1,
  };
}
