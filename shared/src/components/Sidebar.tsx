import { type CSSProperties } from "react";

export type Page = "journals" | "library" | "bookmarks" | "queue" | "settings" | "admin";

interface Props {
  current: Page;
  onNavigate: (page: Page) => void;
  isAdmin?: boolean;
  onSignOut: () => void;
}

const NAV_ITEMS: { page: Page; label: string; icon: string }[] = [
  { page: "journals",  label: "Journals",  icon: "◎" },
  { page: "library",   label: "Library",   icon: "▤" },
  { page: "bookmarks", label: "Bookmarks", icon: "◈" },
  { page: "queue",     label: "Queue",     icon: "↓" },
  { page: "settings",  label: "Settings",  icon: "⚙" },
];

const sidebar: CSSProperties = {
  width: 220, minWidth: 220, height: "100vh", position: "sticky", top: 0,
  display: "flex", flexDirection: "column",
  background: "var(--color-bg-dark, #1A2332)",
  padding: "0 0 1rem 0", userSelect: "none", flexShrink: 0,
};
const logoWrap: CSSProperties = {
  padding: "1.5rem 1.25rem 1.25rem",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  marginBottom: "0.625rem",
};
const logoMain: CSSProperties = {
  fontFamily: "'Playfair Display', Georgia, serif",
  fontWeight: 700, fontSize: "1.05rem", letterSpacing: "-0.01em",
  color: "var(--color-text-on-dark, #E8E0D4)", lineHeight: 1.2,
};
const logoSub: CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontWeight: 400, fontSize: "0.65rem", letterSpacing: "0.12em",
  textTransform: "uppercase" as const,
  color: "var(--color-text-on-dark-muted, #9EA8B8)", marginTop: "0.2rem",
};
const navStyle: CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column", padding: "0 0.75rem", gap: 2,
};
const divider: CSSProperties = {
  borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0.5rem 0.75rem",
};
const signOutStyle: CSSProperties = {
  margin: "0 0.75rem", padding: "0.55rem 0.875rem",
  display: "flex", alignItems: "center", gap: "0.625rem",
  cursor: "pointer", borderRadius: "0.25rem",
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontWeight: 500, fontSize: "0.8rem",
  color: "rgba(232,224,212,0.5)", background: "transparent", border: "none",
  width: "calc(100% - 1.5rem)", textAlign: "left" as const,
  transition: "color 0.15s",
};
const iconStyle: CSSProperties = {
  fontSize: "0.9rem", width: 18, textAlign: "center" as const,
  flexShrink: 0, opacity: 0.8,
};

const itemStyle = (active: boolean): CSSProperties => ({
  display: "flex", alignItems: "center", gap: "0.625rem",
  padding: "0.55rem 0.875rem", borderRadius: "0.25rem", cursor: "pointer",
  fontFamily: "'DM Sans', system-ui, sans-serif", fontWeight: active ? 600 : 400,
  fontSize: "0.825rem",
  color: active ? "var(--color-accent-light, #F0D4B4)" : "var(--color-text-on-dark, #E8E0D4)",
  background: active ? "rgba(192,120,58,0.18)" : "transparent",
  borderLeft: active ? "2px solid var(--color-accent, #C0783A)" : "2px solid transparent",
  transition: "background 0.12s, color 0.12s",
});

export function Sidebar({ current, onNavigate, isAdmin, onSignOut }: Props) {
  const items = isAdmin
    ? [...NAV_ITEMS, { page: "admin" as Page, label: "Admin", icon: "◉" }]
    : NAV_ITEMS;

  return (
    <aside style={sidebar}>
      <div style={logoWrap}>
        <div style={logoMain}>Journal Club</div>
        <div style={logoSub}>Academic Library</div>
      </div>

      <nav style={navStyle}>
        {items.map(({ page, label, icon }) => (
          <div
            key={page}
            style={itemStyle(current === page)}
            onClick={() => onNavigate(page)}
          >
            <span style={iconStyle}>{icon}</span>
            {label}
          </div>
        ))}
      </nav>

      <div style={divider} />
      <button style={signOutStyle} onClick={onSignOut}>
        <span style={{ ...iconStyle, opacity: 0.5 }}>↩</span>
        Sign out
      </button>
    </aside>
  );
}
