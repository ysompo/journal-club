import { useState, FormEvent } from "react";
import { saveApiUrl } from "../store/auth";

interface Props {
  onConnected: () => void;
}

export function ServerSetupScreen({ onConnected }: Props) {
  const [url, setUrl] = useState("https://");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "fail" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function testConnection(rawUrl: string): Promise<boolean> {
    const clean = rawUrl.replace(/\/$/, "");
    try {
      const res = await fetch(`${clean}/health`, { signal: AbortSignal.timeout(5000) });
      return res.ok;
    } catch {
      return false;
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const clean = url.trim().replace(/\/$/, "");
    if (!clean.startsWith("http")) {
      setError("URL must start with http:// or https://");
      return;
    }
    setTesting(true);
    setError(null);
    setTestResult(null);
    const ok = await testConnection(clean);
    setTesting(false);
    if (!ok) {
      setTestResult("fail");
      setError("Could not reach the server. Check the URL and try again.");
      return;
    }
    setTestResult("ok");
    saveApiUrl(clean);
    onConnected();
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem 0.75rem",
    border: "1px solid var(--color-outline-variant)",
    borderRadius: "var(--radius)",
    background: "var(--color-surface)",
    color: "var(--color-on-surface)",
    fontFamily: "var(--font-body)",
    fontSize: "0.9375rem",
    outline: "none",
    boxSizing: "border-box",
  };

  return (
    <main style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--color-surface)" }}>
      <div style={{ width: "100%", maxWidth: 440, padding: "2rem" }}>
        <h1 style={{ fontFamily: "var(--font-headline)", fontSize: "2rem", color: "var(--color-primary)", textAlign: "center", marginBottom: "0.25rem" }}>
          Journal Club
        </h1>
        <p style={{ color: "var(--color-on-surface-variant)", textAlign: "center", fontSize: "0.875rem", marginBottom: "2rem" }}>
          Enter the server URL provided by your administrator
        </p>

        <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1.5rem" }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              <label style={{ fontSize: "0.8125rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", fontWeight: 500 }}>
                Server URL
              </label>
              <input
                type="url"
                value={url}
                onChange={e => { setUrl(e.target.value); setTestResult(null); setError(null); }}
                required
                autoFocus
                placeholder="https://your-server.example.com"
                style={inputStyle}
              />
            </div>

            {error && (
              <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p>
            )}
            {testResult === "ok" && (
              <p style={{ color: "var(--color-primary)", fontSize: "0.85rem", margin: 0 }}>✓ Connected successfully</p>
            )}

            <button
              type="submit"
              disabled={testing || !url.trim()}
              style={{ padding: "0.625rem 1rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.9375rem", fontWeight: 500, cursor: "pointer", opacity: testing || !url.trim() ? 0.6 : 1 }}
            >
              {testing ? "Testing connection…" : "Connect"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
