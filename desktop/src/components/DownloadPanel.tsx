import { useState } from "react";
import type { ActiveDownload } from "../hooks/useQueuePoller";
import type { QueueItem } from "@jc/shared";

interface Props {
  activeDownloads: ActiveDownload[];
  queuedItems: QueueItem[];
  failedItems: QueueItem[];
  onCancel: (id: string) => void;
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

export function DownloadPanel(props: Props) {
  const activeDownloads = props.activeDownloads ?? [];
  const queuedItems = props.queuedItems ?? [];
  const failedItems = props.failedItems ?? [];
  const { onCancel, onRetry, onDelete, onReport } = props;

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setExpanded(e => ({ ...e, [id]: !e[id] }));
  const copy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  if (activeDownloads.length === 0 && queuedItems.length === 0 && failedItems.length === 0) return null;

  return (
    <div style={s.panel}>
      {activeDownloads.map(d => {
        const key = `active-${d.queueItemId}`;
        const isExpanded = !!expanded[key];
        const errText = [d.messages.join("\n"), d.errorMsg].filter(Boolean).join("\n\n") || "";
        return (
          <div key={key} style={{ ...s.row, flexDirection: "column", alignItems: "stretch" }}>
            <div style={s.row}>
              <span style={s.label}>
                {d.status === "downloading" && "⏳ "}
                {d.status === "done" && "✓ "}
                {d.status === "error" && "✗ "}
                {d.input}
              </span>
              <span style={s.badge(d.status === "done" ? "green" : d.status === "error" ? "red" : "neutral")}>
                {d.status}
              </span>
              {d.status === "error" && (
                <>
                  <button style={s.btn} onClick={() => toggle(key)}>{isExpanded ? "Hide" : "Details"}</button>
                  <button style={s.btn} onClick={() => copy(errText)}>Copy</button>
                  <button style={s.btn} onClick={() => onReport(d.queueItemId)}>Send Report</button>
                </>
              )}
              {d.status === "downloading" && (
                <button
                  style={{ ...s.btn, borderColor: "var(--color-error)", color: "var(--color-error)" }}
                  onClick={() => onCancel(d.queueItemId)}
                >
                  Cancel
                </button>
              )}
            </div>
            {d.status === "error" && isExpanded && errText && (
              <pre style={{ margin: "0.25rem 0 0 0", padding: "0.5rem", background: "var(--color-surface-container-high)", borderRadius: "var(--radius)", color: "var(--color-error)", fontSize: "0.7rem", whiteSpace: "pre-wrap", wordBreak: "break-word", userSelect: "text" }}>
                {errText}
              </pre>
            )}
            {d.status === "downloading" && d.messages.length > 0 && (
              <div style={{ color: "var(--color-on-surface-variant)", fontSize: "0.7rem", marginTop: "0.25rem", paddingLeft: "1rem" }}>
                {d.messages[d.messages.length - 1]}
              </div>
            )}
          </div>
        );
      })}

      {queuedItems.map(item => (
        <div key={`queued-${item.id}`} style={s.row}>
          <span style={s.label}>
            {item.input.length > 60 ? item.input.slice(0, 60) + "…" : item.input}
          </span>
          <span style={s.badge("neutral")}>queued</span>
          <button style={s.btn} onClick={() => onCancel(item.id)}>Cancel</button>
        </div>
      ))}

      {failedItems.map(item => {
        const key = `failed-${item.id}`;
        const isExpanded = !!expanded[key];
        return (
          <div key={key} style={{ ...s.row, flexDirection: "column", alignItems: "stretch" }}>
            <div style={s.row}>
              <span style={s.label}>✗ {item.input}</span>
              <span style={s.badge("red")}>failed {item.retry_count}×</span>
              {item.error && (
                <>
                  <button style={s.btn} onClick={() => toggle(key)}>{isExpanded ? "Hide" : "Details"}</button>
                  <button style={s.btn} onClick={() => copy(item.error ?? "")}>Copy</button>
                </>
              )}
              <button style={s.btn} onClick={() => onRetry(item.id)}>Retry</button>
              <button style={s.btn} onClick={() => onReport(item.id)}>Report</button>
              <button
                style={{ ...s.btn, borderColor: "var(--color-error)", color: "var(--color-error)" }}
                onClick={() => onDelete(item.id)}
              >
                Delete
              </button>
            </div>
            {isExpanded && item.error && (
              <pre style={{ margin: "0.25rem 0 0 0", padding: "0.5rem", background: "var(--color-surface-container-high)", borderRadius: "var(--radius)", color: "var(--color-error)", fontSize: "0.7rem", whiteSpace: "pre-wrap", wordBreak: "break-word", userSelect: "text" }}>
                {item.error}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
