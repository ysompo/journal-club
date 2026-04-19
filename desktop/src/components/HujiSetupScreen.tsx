import { useState, FormEvent } from "react";

interface Props {
  onSave: (email: string, password: string, chromeProfile: string) => Promise<void>;
}

export function HujiSetupScreen({ onSave }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [chromeProfile, setChromeProfile] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onSave(email, password, chromeProfile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      className="flex items-center justify-center min-h-screen"
      style={{ background: "var(--color-surface)" }}
    >
      <div style={{ width: "100%", maxWidth: 440, padding: "2rem" }}>
        <h1
          style={{
            fontFamily: "var(--font-headline)",
            fontSize: "1.75rem",
            color: "var(--color-primary)",
            marginBottom: "0.375rem",
            textAlign: "center",
          }}
        >
          HUJI credentials
        </h1>
        <p
          style={{
            color: "var(--color-on-surface-variant)",
            textAlign: "center",
            fontSize: "0.875rem",
            marginBottom: "1.5rem",
          }}
        >
          Stored securely in your OS keychain — never sent to the server.
        </p>

        <div
          style={{
            background: "var(--color-surface-container-lowest)",
            border: "1px solid var(--color-outline-variant)",
            borderRadius: "var(--radius-lg)",
            padding: "1.5rem",
          }}
        >
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="HUJI email">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                placeholder="username@mail.huji.ac.il"
                style={inputStyle}
              />
            </Field>

            <Field label="HUJI password">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                style={inputStyle}
              />
            </Field>

            <Field label="Chrome profile path (for downloading)">
              <input
                type="text"
                value={chromeProfile}
                onChange={(e) => setChromeProfile(e.target.value)}
                placeholder="C:\Users\you\AppData\Local\Google\Chrome\User Data\Default"
                style={inputStyle}
              />
              <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--color-on-surface-variant)" }}>
                Leave blank to use a temporary profile.
              </p>
            </Field>

            {error && (
              <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} style={primaryButtonStyle}>
              {loading ? "Saving…" : "Save and continue"}
            </button>
          </form>
        </div>
      </div>
    </main>
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
  padding: "0.5rem 0.75rem",
  border: "1px solid var(--color-outline-variant)",
  borderRadius: "var(--radius)",
  background: "var(--color-surface)",
  color: "var(--color-on-surface)",
  fontFamily: "var(--font-body)",
  fontSize: "0.9375rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const primaryButtonStyle: React.CSSProperties = {
  padding: "0.625rem 1rem",
  background: "var(--color-primary)",
  color: "var(--color-on-primary)",
  border: "none",
  borderRadius: "var(--radius)",
  fontFamily: "var(--font-label)",
  fontSize: "0.9375rem",
  fontWeight: 500,
  cursor: "pointer",
  marginTop: "0.25rem",
};
