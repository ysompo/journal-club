import React, { useState, useEffect, useCallback } from "react";
import type { JournalClubApi } from "../api";
import type { QueueItem } from "../types";

interface Props {
  api: JournalClubApi;
}

const STATUS_COLORS: Record<string, string> = {
  queued:      "var(--color-accent, #C0783A)",
  claimed:     "var(--color-text-secondary, #5A6475)",
  downloading: "var(--color-text-secondary, #5A6475)",
  done:        "var(--color-success, #2E6B4F)",
  failed:      "var(--color-error, #9B2C2C)",
};

const STATUS_BG: Record<string, string> = {
  queued:      "var(--color-accent-light, #F0D4B4)",
  claimed:     "var(--color-bg, #F5F0E8)",
  downloading: "var(--color-bg, #F5F0E8)",
  done:        "var(--color-success-bg, #D4EDE2)",
  failed:      "var(--color-error-bg, #F7DCDC)",
};

const STATUS_LABELS: Record<string, string> = {
  queued:      "Queued",
  claimed:     "Claimed",
  downloading: "Downloading…",
  done:        "Done",
  failed:      "Failed",
};

export function QueuePage({ api }: Props) {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [desktopOnline, setDesktopOnline] = useState<boolean | null>(null);

  const refresh = useCallback(() => {
    api.getQueue().then(setQueue).catch(() => {}).finally(() => setLoading(false));
    api.desktopOnlineStatus().then(s => setDesktopOnline(s.online)).catch(() => {});
  }, [api]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, [refresh]);

  const active = queue.filter(q => q.status !== "done" && q.status !== "failed");
  const failed = queue.filter(q => q.status === "failed");
  const done   = queue.filter(q => q.status === "done").slice(0, 20);

  const handleRetry = async (id: string) => { await api.retryQueueItem(id); refresh(); };
  const handleDelete = async (id: string) => { await api.deleteQueueItem(id); refresh(); };
  const handleReport = async (id: string) => { await api.reportFailure(id); refresh(); };

  const fmtDate = (s: string) => new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div style={{ padding: "1.75rem 2rem", maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <h1 style={h1}>Queue</h1>
        <span style={{
          fontSize: "0.75rem",
          fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
          fontWeight: 500,
          padding: "0.25rem 0.75rem",
          borderRadius: "1rem",
          background: desktopOnline === true
            ? "var(--color-success-bg, #D4EDE2)"
            : desktopOnline === false
            ? "var(--color-error-bg, #F7DCDC)"
            : "var(--color-bg, #F5F0E8)",
          color: desktopOnline === true
            ? "var(--color-success, #2E6B4F)"
            : desktopOnline === false
            ? "var(--color-error, #9B2C2C)"
            : "var(--color-text-secondary, #5A6475)",
          border: "1px solid transparent",
        }}>
          Desktop: {desktopOnline === true ? "Online" : desktopOnline === false ? "Offline" : "Unknown"}
        </span>
      </div>

      {loading && <div style={emptyStyle}>Loading…</div>}

      {!loading && active.length === 0 && failed.length === 0 && done.length === 0 && (
        <div style={emptyStyle}>Queue is empty.</div>
      )}

      {active.length > 0 && (
        <Section title="Active">
          {active.map((item, i) => (
            <QueueRow
              key={item.id}
              item={item}
              position={i + 1}
              onRetry={() => handleRetry(item.id)}
              onDelete={() => handleDelete(item.id)}
              onReport={() => handleReport(item.id)}
              fmtDate={fmtDate}
            />
          ))}
        </Section>
      )}

      {failed.length > 0 && (
        <Section title="Failed">
          {failed.map(item => (
            <QueueRow
              key={item.id}
              item={item}
              onRetry={() => handleRetry(item.id)}
              onDelete={() => handleDelete(item.id)}
              onReport={() => handleReport(item.id)}
              fmtDate={fmtDate}
            />
          ))}
        </Section>
      )}

      {done.length > 0 && (
        <Section title="Recently completed">
          {done.map(item => (
            <QueueRow
              key={item.id}
              item={item}
              onDelete={() => handleDelete(item.id)}
              onRetry={() => {}}
              onReport={() => {}}
              fmtDate={fmtDate}
            />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: "2rem" }}>
      <h2 style={sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

function QueueRow({ item, position, onRetry, onDelete, onReport, fmtDate }: {
  item: QueueItem;
  position?: number;
  onRetry: () => void;
  onDelete: () => void;
  onReport: () => void;
  fmtDate: (s: string) => string;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: "0.75rem",
      borderBottom: "1px solid var(--color-border-light, #EDE6DA)",
      padding: "0.75rem 0",
    }}>
      {position != null && (
        <span style={{
          width: 24, textAlign: "center",
          color: "var(--color-text-secondary, #5A6475)",
          fontSize: "0.75rem", paddingTop: "0.1rem", flexShrink: 0,
          fontFamily: "var(--font-mono, monospace)",
        }}>
          {position}
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: "0.875rem",
          fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
          color: "var(--color-text-primary, #1A2332)",
          wordBreak: "break-all",
        }}>
          {item.input}
        </div>
        {item.error && (
          <div style={{
            fontSize: "0.75rem",
            color: "var(--color-error, #9B2C2C)",
            marginTop: "0.2rem",
            fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
          }}>
            {item.error}
          </div>
        )}
        <div style={{
          fontSize: "0.7rem",
          color: "var(--color-text-secondary, #5A6475)",
          marginTop: "0.2rem",
          fontFamily: "var(--font-mono, monospace)",
        }}>
          {fmtDate(item.created_at)} · retries: {item.retry_count}
        </div>
      </div>
      <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0, alignItems: "center" }}>
        <span style={{
          fontSize: "0.7rem", padding: "0.2rem 0.55rem", borderRadius: "1rem",
          fontFamily: "var(--font-label, 'DM Sans', sans-serif)", fontWeight: 500,
          color: STATUS_COLORS[item.status] ?? "inherit",
          background: STATUS_BG[item.status] ?? "var(--color-bg, #F5F0E8)",
        }}>
          {STATUS_LABELS[item.status] ?? item.status}
        </span>
        {item.status === "failed" && (
          <>
            <button onClick={onRetry} style={actionBtn("var(--color-accent, #C0783A)")}>Retry</button>
            <button onClick={onReport} style={actionBtn("var(--color-text-secondary, #5A6475)")}>Report</button>
          </>
        )}
        {(item.status === "queued" || item.status === "done" || item.status === "failed") && (
          <button onClick={onDelete} style={actionBtn("var(--color-text-secondary, #5A6475)")}>✕</button>
        )}
      </div>
    </div>
  );
}

function actionBtn(color: string): React.CSSProperties {
  return {
    background: "none", border: `1px solid ${color}`, borderRadius: "0.2rem",
    cursor: "pointer", color, fontSize: "0.7rem", padding: "0.2rem 0.5rem",
    fontFamily: "var(--font-label, 'DM Sans', sans-serif)", fontWeight: 500,
  };
}

const h1: React.CSSProperties = {
  fontFamily: "var(--font-headline, 'Playfair Display', Georgia, serif)",
  fontWeight: 700, fontSize: "1.6rem", margin: 0,
  color: "var(--color-text-primary, #1A2332)",
};
const sectionTitle: React.CSSProperties = {
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  fontWeight: 600, fontSize: "0.75rem",
  textTransform: "uppercase", letterSpacing: "0.08em",
  color: "var(--color-text-secondary, #5A6475)",
  marginBottom: "0.5rem",
};
const emptyStyle: React.CSSProperties = {
  color: "var(--color-text-secondary, #5A6475)",
  fontSize: "0.875rem",
  fontFamily: "var(--font-label, 'DM Sans', sans-serif)",
  padding: "2.5rem 0", textAlign: "center",
};
