import { useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Props {
  message: string;
  queueItemId: string;
  onDismiss: () => void;
}

const AUTO_DISMISS_MS = 90_000;

export function CloudflareAlertModal({ message, queueItemId, onDismiss }: Props) {
  useEffect(() => {
    const t = setTimeout(onDismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 250 }}>
      <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid #C7820F", borderRadius: "var(--radius-lg)", padding: "1.5rem", width: "100%", maxWidth: 460, boxShadow: "0 8px 32px rgba(0,0,0,0.2)" }}>
        <h2 style={{ fontFamily: "var(--font-headline)", fontSize: "1.1rem", color: "#C7820F", margin: "0 0 0.5rem" }}>
          Human Verification Needed
        </h2>
        <p style={{ margin: "0 0 1.25rem", fontSize: "0.85rem", lineHeight: 1.45, color: "var(--color-on-surface)" }}>
          {message}
        </p>
        <p style={{ margin: "0 0 1.25rem", fontSize: "0.75rem", color: "var(--color-on-surface-variant)" }}>
          The download will resume automatically once you pass the challenge. This alert dismisses after 90 seconds.
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
          <button
            type="button"
            onClick={() => invoke("bring_download_to_front", { queueItemId })}
            style={{ padding: "0.45rem 1rem", background: "var(--color-surface-container, #f0f0f0)", color: "var(--color-on-surface)", border: "1px solid var(--color-outline, #ccc)", borderRadius: "var(--radius)", cursor: "pointer", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500 }}
          >
            Show Chrome Window
          </button>
          <button
            type="button"
            onClick={onDismiss}
            style={{ padding: "0.45rem 1rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", cursor: "pointer", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500 }}
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
