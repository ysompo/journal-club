import { useState } from "react";

interface Props {
  currentEmail: string;
  currentChromeProfile: string;
  onSave: (email: string, password: string, chromeProfile: string) => Promise<void>;
  onDismiss: () => void;
}

export function HujiReauthModal({ currentEmail, currentChromeProfile, onSave, onDismiss }: Props) {
  const [email, setEmail] = useState(currentEmail);
  const [password, setPassword] = useState("");
  const [chromeProfile, setChromeProfile] = useState(currentChromeProfile);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(email.trim(), password, chromeProfile.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credentials");
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem 0.75rem",
    border: "1px solid var(--color-outline-variant)",
    borderRadius: "var(--radius)",
    background: "var(--color-surface-container)",
    color: "var(--color-on-surface)",
    fontFamily: "var(--font-body)",
    fontSize: "0.875rem",
    outline: "none",
    boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: "0.75rem",
    fontFamily: "var(--font-label)",
    color: "var(--color-on-surface-variant)",
    marginBottom: "0.35rem",
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
      <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-error)", borderRadius: "var(--radius-lg)", padding: "1.5rem", width: "100%", maxWidth: 420, boxShadow: "0 8px 32px rgba(0,0,0,0.2)" }}>
        <h2 style={{ fontFamily: "var(--font-headline)", fontSize: "1.1rem", color: "var(--color-error)", margin: "0 0 0.5rem" }}>
          HUJI credentials failed
        </h2>
        <p style={{ margin: "0 0 1.25rem", fontSize: "0.8rem", color: "var(--color-on-surface-variant)" }}>
          A download failed due to an authentication error. Please re-enter your HUJI credentials.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div>
            <label style={labelStyle}>HUJI email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} autoFocus />
          </div>
          <div>
            <label style={labelStyle}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={inputStyle} placeholder="Enter your HUJI password" />
          </div>
          <div>
            <label style={labelStyle}>Chrome profile path (optional)</label>
            <input type="text" value={chromeProfile} onChange={e => setChromeProfile(e.target.value)} style={inputStyle} placeholder="e.g. C:\Users\you\AppData\Local\Google\Chrome\User Data\Default" />
          </div>

          {error && <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-error)" }}>{error}</p>}

          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" onClick={onDismiss} style={{ padding: "0.45rem 0.875rem", background: "none", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", cursor: "pointer", fontFamily: "var(--font-label)", fontSize: "0.8rem", color: "var(--color-on-surface-variant)" }}>
              Dismiss
            </button>
            <button type="submit" disabled={saving || !email.trim() || !password} style={{ padding: "0.45rem 1rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", cursor: "pointer", fontFamily: "var(--font-label)", fontSize: "0.8rem", fontWeight: 500, opacity: saving || !email.trim() || !password ? 0.5 : 1 }}>
              {saving ? "Saving…" : "Save & retry"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
