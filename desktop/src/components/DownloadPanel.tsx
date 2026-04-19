import type { ActiveDownload } from "../hooks/useQueuePoller";
import type { QueueItem } from "@jc/shared";

interface Props {
  activeDownloads: ActiveDownload[];
  failedItems: QueueItem[];
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
  onReport: (id: string) => void;
}

const s = {
  panel: {
    borderTop: "1px solid var(--color-outline-variant)",
    background: "var(--color-surface-container-lowest)",
    padding: "0.625rem 1.5rem",
    fontSize: "0.8rem",
    fontFamily: "var(--font-body)",
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.375rem",
    maxHeight: 220,
    overflowY: "auto" as const,
  },
  row: {
    display: "flex",
    alignItems: "flex-start",
    gap: "0.5rem",
  },
  label: {
    flex: 1,
    minWidth: 0,
    color: "var(--color-on-surface-variant)",
    whiteSpace: "nowrap" as const,
    overflow: "hidden" as const,
    textOverflow: "ellipsis" as const,
  },
  badge: (color: string) => ({
    fontSize: "0.65rem",
    padding: "0.1rem 0.4rem",
    borderRadius: "var(--radius)",
    fontFamily: "var(--font-label)" as const,
    fontWeight: 500,
    flexShrink: 0,
    background: color === "green" ? "var(--color-primary-fixed)" : color === "red" ? "var(--color-error-container)" : "var(--color-surface-container-high)",
    color: color === "green" ? "var(--color-primary)" : color === "red" ? "var(--color-error)" : "var(--color-on-surface-variant)",
  }),
  btn: {
    fontSize: "0.7rem",
    padding: "0.1rem 0.4rem",
    border: "1px solid var(--color-outline-variant)",
    borderRadius: "var(--radius)",
    background: "none",
    cursor: "pointer",
    fontFamily: "var(--font-label)",
    color: "var(--color-on-surface-variant)",
    flexShrink: 0,
  } as React.CSSProperties,
};

export function DownloadPanel({ activeDownloads, failedItems, onRetry, onDelete, onReport }: Props) {
  if (activeDownloads.length === 0 && failedItems.length === 0) return null;

  return (
    <div style={s.panel}>
      {activeDownloads.map(d => (
        <div key={d.queueItemId} style={s.row}>
          <span style={s.label}>
            {d.status === "downloading" && "⏳ "}
            {d.status === "done" && "✓ "}
            {d.status === "error" && "✗ "}
            {d.input.length > 60 ? d.input.slice(0, 60) + "…" : d.input}
          </span>
          <span style={s.badge(d.status === "done" ? "green" : d.status === "error" ? "red" : "neutral")}>
            {d.status === "downloading" ? "downloading" : d.status}
          </span>
          {d.status === "downloading" && d.messages.length > 0 && (
            <span style={{ color: "var(--color-on-surface-variant)", fontSize: "0.7rem", flexShrink: 0, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {d.messages[d.messages.length - 1]}
            </span>
          )}
        </div>
      ))}

      {failedItems.map(item => (
        <div key={item.id} style={s.row}>
          <span style={s.label} title={item.error ?? ""}>
            ✗ {item.input.length > 50 ? item.input.slice(0, 50) + "…" : item.input}
            {item.error && (
              <span style={{ color: "var(--color-error)", marginLeft: "0.25rem" }}>
                — {item.error.slice(0, 60)}
              </span>
            )}
          </span>
          <span style={s.badge("red")}>failed {item.retry_count}×</span>
          <button style={s.btn} onClick={() => onRetry(item.id)}>Retry</button>
          <button style={s.btn} onClick={() => onReport(item.id)} title="Email report to admin">Report</button>
          <button
            style={{ ...s.btn, borderColor: "var(--color-error)", color: "var(--color-error)" }}
            onClick={() => onDelete(item.id)}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  );
}
