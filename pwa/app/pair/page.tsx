"use client";
import { useState, FormEvent, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@jc/shared";
import { saveToken } from "../lib/auth";

function PairForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [token, setToken] = useState(params.get("code") ?? "");
  const [label, setLabel] = useState("tablet");

  // Auto-submit if code was in the QR deep-link URL
  useEffect(() => {
    const code = params.get("code");
    if (code) handleAutoSubmit(code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleAutoSubmit(code: string) {
    setLoading(true);
    try {
      const res = await api.pairTablet(code.trim(), "tablet");
      saveToken(res.access_token);
      router.push("/archive");
    } catch {
      // Show form with pre-filled code on failure
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.pairTablet(token.trim(), label || "tablet");
      saveToken(res.access_token);
      router.push("/archive");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 401
            ? "Code is invalid or has expired. Generate a new one from the desktop app."
            : err.message
          : "Pairing failed"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100dvh", background: "var(--color-surface)", padding: "1rem" }}>
      <div style={{ width: "100%", maxWidth: 380 }}>
        <h1 style={{ fontFamily: "var(--font-headline)", fontSize: "2rem", color: "var(--color-primary)", textAlign: "center", marginBottom: "0.25rem" }}>
          Pair this device
        </h1>
        <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", fontSize: "0.875rem", marginBottom: "1.75rem" }}>
          Open Journal Club on your desktop → click <strong>Pair tablet</strong> → enter the code shown.
        </p>

        <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1.5rem" }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="Pairing code">
              <input
                type="text"
                value={token}
                onChange={e => setToken(e.target.value)}
                required autoFocus
                placeholder="Paste the code from the desktop app"
                style={{ ...inputStyle, fontFamily: "monospace", letterSpacing: "0.05em" }}
                autoComplete="off" autoCorrect="off" spellCheck={false}
              />
            </Field>
            <Field label="Name this device (optional)">
              <input
                type="text"
                value={label}
                onChange={e => setLabel(e.target.value)}
                placeholder="tablet"
                style={inputStyle}
              />
            </Field>
            {error && <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p>}
            <button type="submit" disabled={loading || !token.trim()} style={{ ...primaryBtn, opacity: !token.trim() ? 0.5 : 1 }}>
              {loading ? "Pairing…" : "Pair device"}
            </button>
          </form>
        </div>

        <p style={{ textAlign: "center", marginTop: "1.25rem", fontSize: "0.875rem", color: "var(--color-on-surface-variant)" }}>
          <Link href="/login" style={{ color: "var(--color-primary)", textDecoration: "underline" }}>
            ← Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

export default function PairPage() {
  return (
    <Suspense>
      <PairForm />
    </Suspense>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
      <label style={{ fontSize: "0.8125rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", fontWeight: 500 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem", border: "1px solid var(--color-outline-variant)",
  borderRadius: "var(--radius)", background: "var(--color-surface)",
  color: "var(--color-on-surface)", fontFamily: "var(--font-body)",
  fontSize: "0.9375rem", outline: "none", width: "100%", boxSizing: "border-box",
};

const primaryBtn: React.CSSProperties = {
  padding: "0.625rem 1rem", background: "var(--color-primary)",
  color: "var(--color-on-primary)", border: "none",
  borderRadius: "var(--radius)", fontFamily: "var(--font-label)",
  fontSize: "0.9375rem", fontWeight: 500, cursor: "pointer", marginTop: "0.25rem",
};
