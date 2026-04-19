"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@jc/shared";
import { saveToken } from "../lib/auth";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [hujiUsername, setHujiUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = mode === "login"
        ? await api.login(hujiUsername, password)
        : await api.register(hujiUsername, displayName, password, inviteCode.trim() || undefined);
      saveToken(res.access_token);
      router.push("/archive");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : mode === "login" ? "Sign-in failed" : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100dvh", background: "var(--color-surface)", padding: "1rem" }}>
      <div style={{ width: "100%", maxWidth: 380 }}>
        <h1 style={{ fontFamily: "var(--font-headline)", fontSize: "2rem", color: "var(--color-primary)", textAlign: "center", marginBottom: "0.25rem" }}>
          Journal Club
        </h1>
        <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", fontSize: "0.875rem", marginBottom: "1.75rem" }}>
          {mode === "login" ? "Sign in to your account" : "Create a new account"}
        </p>

        <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1.5rem" }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="HUJI username">
              <input type="text" value={hujiUsername} onChange={e => setHujiUsername(e.target.value)} required autoFocus placeholder="e.g. jsmith" style={inputStyle} />
            </Field>

            {mode === "register" && (
              <Field label="Display name">
                <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="How you appear to others" style={inputStyle} />
              </Field>
            )}

            <Field label="Password">
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" style={inputStyle} />
            </Field>

            {mode === "register" && (
              <Field label="Invite code (if required)">
                <input type="text" value={inviteCode} onChange={e => setInviteCode(e.target.value.toUpperCase())} placeholder="e.g. A3B7F92D" style={{ ...inputStyle, fontFamily: "monospace", letterSpacing: "0.08em" }} />
              </Field>
            )}

            {error && <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p>}
            <button type="submit" disabled={loading} style={primaryBtn}>
              {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>

        <p style={{ textAlign: "center", marginTop: "1rem", fontSize: "0.875rem", color: "var(--color-on-surface-variant)" }}>
          {mode === "login" ? "No account? " : "Already have an account? "}
          <button
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
            style={{ color: "var(--color-primary)", background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline" }}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>

        {mode === "login" && (
          <p style={{ textAlign: "center", marginTop: "0.5rem", fontSize: "0.875rem", color: "var(--color-on-surface-variant)" }}>
            Pairing from the desktop app?{" "}
            <Link href="/pair" style={{ color: "var(--color-primary)", textDecoration: "underline" }}>
              Enter pairing code
            </Link>
          </p>
        )}
      </div>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
      <label style={{ fontSize: "0.8125rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", fontWeight: 500 }}>{label}</label>
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
