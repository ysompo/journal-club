import { useState, useEffect } from "react";
import { api } from "@jc/shared";
import { getVersion } from "@tauri-apps/api/app";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { getApiUrl, saveApiUrl } from "../store/auth";

type UpdateStatus =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "up-to-date" }
  | { state: "available"; version: string; install: () => Promise<void> }
  | { state: "installing" }
  | { state: "error"; message: string };

interface Props {
  onClose: () => void;
  hujiEmail: string;
  onSaveHuji: (email: string, password: string) => Promise<void>;
}

type FontSize = "small" | "medium" | "large";

const btnStyle = (active: boolean): React.CSSProperties => ({
  padding: "0.35rem 0.75rem",
  border: `1px solid ${active ? "var(--color-primary)" : "var(--color-outline-variant)"}`,
  borderRadius: "var(--radius)",
  background: active ? "var(--color-primary)" : "none",
  color: active ? "var(--color-on-primary)" : "var(--color-on-surface-variant)",
  fontFamily: "var(--font-label)",
  fontSize: "0.8rem",
  cursor: "pointer",
});

export function SettingsModal({ onClose, hujiEmail, onSaveHuji }: Props) {
  const [fontSize, setFontSize] = useState<FontSize>("medium");
  const [emails, setEmails] = useState<string[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [serverUrl, setServerUrl] = useState(getApiUrl());
  const [urlSaved, setUrlSaved] = useState(false);
  const [appVersion, setAppVersion] = useState<string>("");
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus>({ state: "idle" });

  const [hujiEmailEdit, setHujiEmailEdit] = useState(hujiEmail);
  const [hujiPassword, setHujiPassword] = useState("");
  const [hujiSaving, setHujiSaving] = useState(false);
  const [hujiSaved, setHujiSaved] = useState(false);
  const [hujiError, setHujiError] = useState<string | null>(null);

  async function saveHuji(e: React.FormEvent) {
    e.preventDefault();
    if (!hujiEmailEdit.trim() || !hujiPassword) return;
    setHujiSaving(true);
    setHujiError(null);
    try {
      await onSaveHuji(hujiEmailEdit.trim(), hujiPassword);
      setHujiPassword("");
      setHujiSaved(true);
      setTimeout(() => setHujiSaved(false), 2500);
    } catch (err) {
      setHujiError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setHujiSaving(false);
    }
  }

  useEffect(() => {
    api.getSettings().then(s => {
      setFontSize(s.font_size as FontSize);
      setEmails(s.email_addresses);
      setLoading(false);
    }).catch(() => setLoading(false));
    getVersion().then(setAppVersion).catch(() => setAppVersion("?"));
  }, []);

  async function checkForUpdates() {
    setUpdateStatus({ state: "checking" });
    try {
      const update = await check();
      if (update?.available) {
        setUpdateStatus({
          state: "available",
          version: update.version,
          install: async () => {
            setUpdateStatus({ state: "installing" });
            try {
              await update.downloadAndInstall();
              await relaunch();
            } catch (e) {
              setUpdateStatus({ state: "error", message: e instanceof Error ? e.message : String(e) });
            }
          },
        });
      } else {
        setUpdateStatus({ state: "up-to-date" });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // Tauri updater throws when there's no valid release (i.e. already up to date)
      if (msg.includes("release") || msg.includes("fetch") || msg.includes("endpoint")) {
        setUpdateStatus({ state: "up-to-date" });
      } else {
        setUpdateStatus({ state: "error", message: msg });
      }
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.updateSettings({ theme: "light", font_size: fontSize, email_addresses: emails });
      onClose();
    } catch {
      setError("Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  function addEmail() {
    const e = newEmail.trim();
    if (!e || emails.includes(e) || emails.length >= 3) return;
    setEmails(prev => [...prev, e]);
    setNewEmail("");
  }

  const label: React.CSSProperties = {
    fontSize: "0.75rem",
    fontFamily: "var(--font-label)",
    color: "var(--color-on-surface-variant)",
    marginBottom: "0.4rem",
    display: "block",
  };

  // Guard against dismissing the modal during an in-flight update install —
  // `downloadAndInstall` is not cancellable and `relaunch` will fire even if
  // the modal unmounts, leaving the user with no progress indicator.
  const isInstalling = updateStatus.state === "installing";
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (isInstalling) return;
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
      onClick={handleBackdropClick}
    >
      <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1.5rem", width: "100%", maxWidth: 420, boxShadow: "0 8px 32px rgba(0,0,0,0.12)" }}>
        <h2 style={{ fontFamily: "var(--font-headline)", fontSize: "1.25rem", color: "var(--color-on-surface)", margin: "0 0 1.25rem" }}>
          Settings
        </h2>

        {loading ? (
          <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>Loading…</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* Font size */}
            <div>
              <span style={label}>Font size</span>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {(["small", "medium", "large"] as FontSize[]).map(f => (
                  <button key={f} style={btnStyle(fontSize === f)} onClick={() => setFontSize(f)}>
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Email addresses */}
            <div>
              <span style={label}>Email addresses for PDF delivery (max 3)</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                {emails.map(e => (
                  <div key={e} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ flex: 1, fontSize: "0.8rem", color: "var(--color-on-surface)", fontFamily: "var(--font-body)" }}>{e}</span>
                    <button
                      onClick={() => setEmails(prev => prev.filter(x => x !== e))}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-error)", fontSize: "0.8rem", padding: "0.1rem 0.3rem" }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {emails.length < 3 && (
                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.25rem" }}>
                    <input
                      type="email"
                      value={newEmail}
                      onChange={e => setNewEmail(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addEmail(); } }}
                      placeholder="email@example.com"
                      style={{ flex: 1, padding: "0.375rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.8rem", outline: "none" }}
                    />
                    <button
                      onClick={addEmail}
                      disabled={!newEmail.trim()}
                      style={{ ...btnStyle(false), opacity: newEmail.trim() ? 1 : 0.5 }}
                    >
                      Add
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* HUJI library credentials */}
            <div>
              <span style={label}>HUJI library credentials</span>
              <form onSubmit={saveHuji} style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <input
                  type="email"
                  value={hujiEmailEdit}
                  onChange={e => setHujiEmailEdit(e.target.value)}
                  placeholder="username@mail.huji.ac.il"
                  required
                  style={{ padding: "0.35rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.8rem", outline: "none" }}
                />
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="password"
                    value={hujiPassword}
                    onChange={e => setHujiPassword(e.target.value)}
                    placeholder="New password"
                    style={{ flex: 1, padding: "0.35rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.8rem", outline: "none" }}
                  />
                  <button
                    type="submit"
                    disabled={hujiSaving || !hujiPassword || !hujiEmailEdit.trim()}
                    style={{ ...btnStyle(false), flexShrink: 0, opacity: (!hujiPassword || !hujiEmailEdit.trim()) ? 0.5 : 1 }}
                  >
                    {hujiSaving ? "Saving…" : hujiSaved ? "Saved!" : "Update"}
                  </button>
                </div>
                {hujiError && <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--color-error)" }}>{hujiError}</p>}
                <p style={{ margin: 0, fontSize: "0.7rem", color: "var(--color-on-surface-variant)" }}>
                  Used only to fetch PDFs through the HUJI library proxy. Stored locally, never sent to the server.
                </p>
              </form>
            </div>

            {/* Server URL */}
            <div>
              <span style={label}>Server URL</span>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="url"
                  value={serverUrl}
                  onChange={e => { setServerUrl(e.target.value); setUrlSaved(false); }}
                  style={{ flex: 1, padding: "0.35rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.8rem", outline: "none" }}
                />
                <button
                  onClick={() => { saveApiUrl(serverUrl.trim()); setUrlSaved(true); setTimeout(() => setUrlSaved(false), 2000); }}
                  style={{ ...btnStyle(false), flexShrink: 0 }}
                >
                  {urlSaved ? "Saved!" : "Update"}
                </button>
              </div>
              <p style={{ margin: "0.3rem 0 0", fontSize: "0.7rem", color: "var(--color-on-surface-variant)" }}>
                Takes effect after restarting the app.
              </p>
            </div>

            {error && <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-error)" }}>{error}</p>}

            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.25rem" }}>
              <button onClick={onClose} disabled={isInstalling} style={{ ...btnStyle(false), opacity: isInstalling ? 0.5 : 1 }}>Cancel</button>
              <button
                onClick={save}
                disabled={saving || isInstalling}
                style={{ ...btnStyle(true), opacity: saving || isInstalling ? 0.6 : 1 }}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>

            <div style={{ borderTop: "1px solid var(--color-outline-variant)", paddingTop: "0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
              <div style={{ fontSize: "0.7rem", color: "var(--color-on-surface-variant)", lineHeight: 1.5 }}>
                <div>Journal Club v{appVersion || "…"}</div>
                {updateStatus.state === "up-to-date" && <div style={{ color: "var(--color-on-surface-variant)" }}>You're up to date.</div>}
                {updateStatus.state === "available" && <div style={{ color: "var(--color-primary)" }}>v{updateStatus.version} is available.</div>}
                {updateStatus.state === "error" && <div style={{ color: "var(--color-error)" }}>{updateStatus.message}</div>}
              </div>
              {updateStatus.state === "available" ? (
                <button onClick={() => updateStatus.install()} style={btnStyle(true)}>
                  Install & relaunch
                </button>
              ) : (
                <button
                  onClick={checkForUpdates}
                  disabled={updateStatus.state === "checking" || updateStatus.state === "installing"}
                  style={btnStyle(false)}
                >
                  {updateStatus.state === "checking" ? "Checking…" : updateStatus.state === "installing" ? "Installing…" : "Check for updates"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
