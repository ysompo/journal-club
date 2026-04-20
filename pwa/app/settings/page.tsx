"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@jc/shared";
import { loadToken, clearToken } from "../lib/auth";

type Theme = "light" | "dark" | "system";
type FontSize = "small" | "medium" | "large";

export default function SettingsPage() {
  const router = useRouter();
  const [theme, setTheme] = useState<Theme>("system");
  const [fontSize, setFontSize] = useState<FontSize>("medium");
  const [emails, setEmails] = useState<string[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSaved, setPwSaved] = useState(false);

  useEffect(() => {
    if (!loadToken()) { router.replace("/login"); return; }
    api.getSettings().then(s => {
      setTheme(s.theme as Theme);
      setFontSize(s.font_size as FontSize);
      setEmails(s.email_addresses);
      setLoading(false);
    }).catch(err => {
      if (err instanceof ApiError && err.status === 401) { clearToken(); router.replace("/login"); }
      else setLoading(false);
    });
  }, [router]);

  // Apply font size to DOM whenever it changes (real-time preview + persists across navigation)
  const FONT_SIZES: Record<FontSize, string> = { small: "14px", medium: "16px", large: "18px" };
  useEffect(() => {
    if (loading) return;
    document.documentElement.style.fontSize = FONT_SIZES[fontSize];
    localStorage.setItem("jc-font-size", fontSize);
  }, [fontSize, loading]);

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateSettings({ theme, font_size: fontSize, email_addresses: emails });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      setError("Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function changePassword() {
    setPwError(null);
    if (!currentPw || !newPw || !confirmPw) { setPwError("All fields required"); return; }
    if (newPw !== confirmPw) { setPwError("Passwords do not match"); return; }
    if (newPw.length < 8) { setPwError("Password must be at least 8 characters"); return; }
    setPwSaving(true);
    try {
      await api.changePassword(currentPw, newPw);
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
      setPwSaved(true);
      setTimeout(() => setPwSaved(false), 2000);
    } catch (err: any) {
      setPwError(err?.message ?? "Failed to change password");
    } finally {
      setPwSaving(false);
    }
  }

  function addEmail() {
    const e = newEmail.trim();
    if (!e || emails.includes(e) || emails.length >= 3) return;
    setEmails(prev => [...prev, e]);
    setNewEmail("");
  }

  const seg = (active: boolean): React.CSSProperties => ({
    padding: "0.45rem 0.875rem",
    border: `1px solid ${active ? "var(--color-primary)" : "var(--color-outline-variant)"}`,
    borderRadius: "var(--radius)",
    background: active ? "var(--color-primary)" : "var(--color-surface-container)",
    color: active ? "var(--color-on-primary)" : "var(--color-on-surface-variant)",
    fontFamily: "var(--font-label)",
    fontSize: "0.875rem",
    cursor: "pointer",
  });

  return (
    <div style={{ minHeight: "100dvh", background: "var(--color-surface)", display: "flex", flexDirection: "column" }}>
      <header style={{ position: "sticky", top: 0, zIndex: 10, background: "var(--color-surface-container-lowest)", borderBottom: "1px solid var(--color-outline-variant)", padding: "0.625rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <button
          onClick={() => router.push("/journals")}
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-primary)", fontFamily: "var(--font-label)", fontSize: "0.875rem", padding: "0.2rem 0" }}
        >
          ← Back
        </button>
        <span style={{ fontFamily: "var(--font-headline)", fontSize: "1.1rem", color: "var(--color-on-surface)", flex: 1 }}>
          Settings
        </span>
      </header>

      <main style={{ flex: 1, padding: "1.25rem 1rem", display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: 480, width: "100%" }}>
        {loading ? (
          <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>Loading…</p>
        ) : (
          <>
            {/* Theme */}
            <section>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Theme
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {(["light", "dark", "system"] as Theme[]).map(t => (
                  <button key={t} style={seg(theme === t)} onClick={() => setTheme(t)}>
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </section>

            {/* Font size */}
            <section>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Text size
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {(["small", "medium", "large"] as FontSize[]).map(f => (
                  <button key={f} style={seg(fontSize === f)} onClick={() => setFontSize(f)}>
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            </section>

            {/* Email addresses */}
            <section>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Email addresses for PDF delivery
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {emails.map(e => (
                  <div key={e} style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "0.5rem 0.75rem", background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)" }}>
                    <span style={{ flex: 1, fontSize: "0.875rem", color: "var(--color-on-surface)", fontFamily: "var(--font-body)" }}>{e}</span>
                    <button
                      onClick={() => setEmails(prev => prev.filter(x => x !== e))}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-error)", fontSize: "0.8rem", padding: "0.1rem 0.25rem", fontFamily: "var(--font-label)" }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {emails.length < 3 && (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <input
                      type="email"
                      value={newEmail}
                      onChange={e => setNewEmail(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addEmail(); } }}
                      placeholder="email@example.com"
                      style={{ flex: 1, padding: "0.5rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.875rem", outline: "none" }}
                    />
                    <button
                      onClick={addEmail}
                      disabled={!newEmail.trim()}
                      style={{ ...seg(false), opacity: newEmail.trim() ? 1 : 0.5 }}
                    >
                      Add
                    </button>
                  </div>
                )}
                <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--color-on-surface-variant)" }}>
                  Max 3 addresses. These receive PDF attachments when you use "Email to self."
                </p>
              </div>
            </section>

            {error && <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--color-error)" }}>{error}</p>}
            {saved && <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--color-primary)" }}>Saved!</p>}

            <button
              onClick={save}
              disabled={saving}
              style={{ alignSelf: "flex-start", padding: "0.5rem 1.25rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.875rem", fontWeight: 500, cursor: "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving…" : "Save settings"}
            </button>
            {/* Change password */}
            <section>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Change Password
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {(["Current password", "New password", "Confirm new password"] as const).map((label, i) => {
                  const val = [currentPw, newPw, confirmPw][i];
                  const setter = [setCurrentPw, setNewPw, setConfirmPw][i];
                  return (
                    <input
                      key={label}
                      type="password"
                      placeholder={label}
                      value={val}
                      onChange={e => setter(e.target.value)}
                      style={{ padding: "0.5rem 0.75rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.875rem", outline: "none" }}
                    />
                  );
                })}
                {pwError && <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--color-error)" }}>{pwError}</p>}
                {pwSaved && <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--color-primary)" }}>Password changed!</p>}
                <button
                  onClick={changePassword}
                  disabled={pwSaving}
                  style={{ alignSelf: "flex-start", padding: "0.5rem 1.25rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.875rem", fontWeight: 500, cursor: "pointer", opacity: pwSaving ? 0.6 : 1 }}
                >
                  {pwSaving ? "Saving…" : "Change password"}
                </button>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
