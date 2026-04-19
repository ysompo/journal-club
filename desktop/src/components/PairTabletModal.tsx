import { useState, useEffect, useRef } from "react";
import QRCode from "qrcode";
import { api } from "@jc/shared";

interface Props {
  onClose: () => void;
  pwaUrl: string; // base URL of the PWA, e.g. https://jc.labor-ai.com
}

type Step = "loading" | "ready" | "error";

export function PairTabletModal({ onClose, pwaUrl }: Props) {
  const [step, setStep] = useState<Step>("loading");
  const [qrToken, setQrToken] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    api.generateQrToken()
      .then(async ({ qr_token, expires_at }) => {
        if (cancelled) return;
        setQrToken(qr_token);
        setExpiresAt(expires_at);
        // Build the deep-link URL the tablet will open
        const pairUrl = `${pwaUrl.replace(/\/$/, "")}/pair?code=${encodeURIComponent(qr_token)}`;
        if (canvasRef.current) {
          await QRCode.toCanvas(canvasRef.current, pairUrl, { width: 220, margin: 1, color: { dark: "#005977", light: "#ffffff" } });
        }
        setStep("ready");
      })
      .catch(e => {
        if (cancelled) return;
        setErrorMsg(e instanceof Error ? e.message : "Failed to generate code");
        setStep("error");
      });
    return () => { cancelled = true; };
  }, [pwaUrl]);

  const minutesLeft = expiresAt
    ? Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 60000))
    : 0;

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1.5rem", width: "100%", maxWidth: 340, boxShadow: "0 8px 32px rgba(0,0,0,0.12)", textAlign: "center" }}>
        <h2 style={{ fontFamily: "var(--font-headline)", fontSize: "1.25rem", color: "var(--color-on-surface)", margin: "0 0 0.25rem" }}>
          Pair tablet
        </h2>
        <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.8125rem", margin: "0 0 1.25rem" }}>
          Open <strong>{pwaUrl}</strong> on your tablet and tap <em>Enter pairing code</em>.
        </p>

        {step === "loading" && (
          <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem", margin: "2rem 0" }}>Generating code…</p>
        )}

        {step === "error" && (
          <p style={{ color: "var(--color-error)", fontSize: "0.875rem", margin: "2rem 0" }}>{errorMsg}</p>
        )}

        {step === "ready" && (
          <>
            {/* QR code */}
            <div style={{ display: "flex", justifyContent: "center", marginBottom: "1rem" }}>
              <canvas ref={canvasRef} style={{ borderRadius: "var(--radius-lg)", border: "1px solid var(--color-outline-variant)" }} />
            </div>

            {/* Manual code */}
            <p style={{ fontSize: "0.75rem", color: "var(--color-on-surface-variant)", marginBottom: "0.375rem" }}>Or enter this code manually:</p>
            <div
              style={{ fontFamily: "monospace", fontSize: "0.8rem", background: "var(--color-surface-container)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", padding: "0.5rem 0.75rem", wordBreak: "break-all", cursor: "pointer", userSelect: "all" }}
              title="Click to copy"
              onClick={() => navigator.clipboard.writeText(qrToken).catch(() => {})}
            >
              {qrToken}
            </div>
            <p style={{ fontSize: "0.7rem", color: "var(--color-on-surface-variant)", marginTop: "0.5rem" }}>
              Expires in ~{minutesLeft} minute{minutesLeft !== 1 ? "s" : ""}. One-time use.
            </p>
          </>
        )}

        <button
          onClick={onClose}
          style={{ marginTop: "1rem", padding: "0.5rem 1.25rem", background: "none", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", cursor: "pointer", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)" }}
        >
          Close
        </button>
      </div>
    </div>
  );
}
