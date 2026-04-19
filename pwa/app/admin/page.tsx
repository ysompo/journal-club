"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@jc/shared";
import { loadToken, clearToken } from "../lib/auth";

type Tab = "stats" | "users" | "reports" | "invites";

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("stats");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [stats, setStats] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [users, setUsers] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [reports, setReports] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [invites, setInvites] = useState<any[]>([]);
  const [newInviteNote, setNewInviteNote] = useState("");
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, u, r, inv] = await Promise.all([
        api.getAdminStats(),
        api.getAdminUsers(),
        api.getAdminReports(false),
        api.listInvites(),
      ]);
      setStats(s);
      setUsers(u);
      setReports(r);
      setInvites(inv);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { clearToken(); router.replace("/login"); }
      else if (err instanceof ApiError && err.status === 403) setError("Admin access required.");
      else setError("Failed to load admin data.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!loadToken()) { router.replace("/login"); return; }
    loadData();
  }, [router, loadData]);

  async function resolveReport(id: string) {
    await api.resolveReport(id);
    setReports(prev => prev.filter(r => r.id !== id));
  }

  async function createInvite() {
    setCreatingInvite(true);
    try {
      const inv = await api.createInvite(newInviteNote.trim() || undefined);
      setInvites(prev => [inv, ...prev]);
      setNewInviteNote("");
    } finally {
      setCreatingInvite(false);
    }
  }

  async function deleteInvite(id: string) {
    await api.deleteInvite(id);
    setInvites(prev => prev.filter(i => i.id !== id));
  }

  async function toggleAdmin(userId: string) {
    const res = await api.toggleAdmin(userId);
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: res.is_admin ? 1 : 0 } : u));
  }

  const tabBtn = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      style={{ padding: "0.5rem 1rem", border: "none", background: tab === t ? "var(--color-primary)" : "var(--color-surface-container)", color: tab === t ? "var(--color-on-primary)" : "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", fontSize: "0.875rem", cursor: "pointer", borderRadius: "var(--radius)" }}
    >
      {label}{t === "reports" && reports.length > 0 ? ` (${reports.length})` : ""}
    </button>
  );

  return (
    <div style={{ minHeight: "100dvh", background: "var(--color-surface)", display: "flex", flexDirection: "column" }}>
      <header style={{ position: "sticky", top: 0, zIndex: 10, background: "var(--color-surface-container-lowest)", borderBottom: "1px solid var(--color-outline-variant)", padding: "0.625rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <button onClick={() => router.push("/archive")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-primary)", fontFamily: "var(--font-label)", fontSize: "0.875rem", padding: "0.2rem 0" }}>
          ← Back
        </button>
        <span style={{ fontFamily: "var(--font-headline)", fontSize: "1.1rem", color: "var(--color-on-surface)", flex: 1 }}>Admin</span>
      </header>

      <main style={{ flex: 1, padding: "1rem" }}>
        {loading && <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>Loading…</p>}
        {error && <p style={{ color: "var(--color-error)", fontSize: "0.875rem" }}>{error}</p>}

        {!loading && !error && (
          <>
            {/* Tabs */}
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
              {tabBtn("stats", "Stats")}
              {tabBtn("users", `Users (${users.length})`)}
              {tabBtn("reports", "Reports")}
              {tabBtn("invites", `Invites (${invites.filter((i: {used_by_name: string|null}) => !i.used_by_name).length} unused)`)}
            </div>

            {/* Stats tab */}
            {tab === "stats" && stats && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
                {[
                  ["Users", stats.users],
                  ["Articles", stats.articles],
                  ["Storage used", fmtBytes(stats.storage_bytes_used)],
                  ["Queued items", stats.queued_items],
                  ["Open reports", stats.open_reports],
                ].map(([label, value]) => (
                  <div key={label as string} style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1rem" }}>
                    <p style={{ margin: "0 0 0.25rem", fontSize: "0.75rem", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)" }}>{label}</p>
                    <p style={{ margin: 0, fontSize: "1.5rem", fontFamily: "var(--font-headline)", color: "var(--color-on-surface)", fontWeight: 600 }}>{value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Users tab */}
            {tab === "users" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {users.map(u => (
                  <div key={u.id} style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "0.875rem 1rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div>
                        <p style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "0.9375rem", color: "var(--color-on-surface)" }}>
                          {u.huji_username}
                          {u.is_admin ? <span style={{ marginLeft: "0.5rem", fontSize: "0.65rem", background: "var(--color-error-container)", color: "var(--color-error)", padding: "0.1rem 0.35rem", borderRadius: "var(--radius)", fontFamily: "var(--font-label)" }}>admin</span> : null}
                        </p>
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--color-on-surface-variant)" }}>
                          {u.article_count} articles · {u.device_count} devices · {fmtBytes(u.storage_bytes_used || 0)} · joined {fmtDate(u.created_at)}
                        </p>
                      </div>
                      <button
                        onClick={() => toggleAdmin(u.id)}
                        style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", cursor: "pointer", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", flexShrink: 0 }}
                      >
                        {u.is_admin ? "Remove admin" : "Make admin"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Invites tab */}
            {tab === "invites" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {/* Create invite */}
                <div style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "1rem", display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                    <label style={{ fontSize: "0.75rem", fontFamily: "var(--font-label)", color: "var(--color-on-surface-variant)" }}>Note (optional)</label>
                    <input
                      type="text"
                      value={newInviteNote}
                      onChange={e => setNewInviteNote(e.target.value)}
                      placeholder="e.g. for Sarah"
                      style={{ padding: "0.4rem 0.625rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "var(--color-surface-container)", color: "var(--color-on-surface)", fontFamily: "var(--font-body)", fontSize: "0.875rem", outline: "none" }}
                    />
                  </div>
                  <button
                    onClick={createInvite}
                    disabled={creatingInvite}
                    style={{ padding: "0.45rem 0.875rem", background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "var(--radius)", fontFamily: "var(--font-label)", fontSize: "0.875rem", cursor: "pointer", flexShrink: 0 }}
                  >
                    {creatingInvite ? "Creating…" : "Create invite"}
                  </button>
                </div>

                {invites.length === 0 && (
                  <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>No invites yet.</p>
                )}
                {invites.map((inv: {id: string; code: string; note: string|null; created_at: string; used_by_name: string|null; used_at: string|null}) => (
                  <div key={inv.id} style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius-lg)", padding: "0.75rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ margin: 0, fontFamily: "monospace", fontSize: "1rem", color: inv.used_by_name ? "var(--color-on-surface-variant)" : "var(--color-on-surface)", letterSpacing: "0.08em", fontWeight: 600 }}>
                        {inv.code}
                        {inv.used_by_name && <span style={{ marginLeft: "0.5rem", fontSize: "0.65rem", fontFamily: "var(--font-label)", letterSpacing: "normal", background: "var(--color-surface-container)", color: "var(--color-on-surface-variant)", padding: "0.1rem 0.35rem", borderRadius: "var(--radius)" }}>used</span>}
                      </p>
                      <p style={{ margin: "0.2rem 0 0", fontSize: "0.75rem", color: "var(--color-on-surface-variant)" }}>
                        {inv.note ? `${inv.note} · ` : ""}{inv.used_by_name ? `Used by ${inv.used_by_name} on ${fmtDate(inv.used_at)}` : `Created ${fmtDate(inv.created_at)}`}
                      </p>
                    </div>
                    {!inv.used_by_name && (
                      <button
                        onClick={() => deleteInvite(inv.id)}
                        style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", cursor: "pointer", color: "var(--color-error)", fontFamily: "var(--font-label)", flexShrink: 0 }}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Reports tab */}
            {tab === "reports" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {reports.length === 0 && (
                  <p style={{ color: "var(--color-on-surface-variant)", fontSize: "0.875rem" }}>No open reports.</p>
                )}
                {reports.map(r => (
                  <div key={r.id} style={{ background: "var(--color-surface-container-lowest)", border: "1px solid var(--color-error)", borderRadius: "var(--radius-lg)", padding: "0.875rem 1rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-on-surface)", fontFamily: "var(--font-label)", fontWeight: 500 }}>
                          {r.huji_username} · {fmtDate(r.occurred_at)}
                        </p>
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--color-on-surface-variant)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          Input: {r.queue_input}
                        </p>
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--color-error)" }}>
                          [{r.error_step}] {r.error_message?.slice(0, 120)}
                        </p>
                        {r.publisher && (
                          <p style={{ margin: "0.2rem 0 0", fontSize: "0.7rem", color: "var(--color-on-surface-variant)" }}>
                            Publisher: {r.publisher}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => resolveReport(r.id)}
                        style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", border: "1px solid var(--color-outline-variant)", borderRadius: "var(--radius)", background: "none", cursor: "pointer", color: "var(--color-on-surface-variant)", fontFamily: "var(--font-label)", flexShrink: 0 }}
                      >
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
