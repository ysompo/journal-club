"use client";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar, type Page } from "@jc/shared/components";
import { clearToken, loadToken } from "../lib/auth";
import { useEffect, useState } from "react";
import { api } from "@jc/shared";

const PATH_TO_PAGE: Record<string, Page> = {
  "/journals":  "journals",
  "/library":   "library",
  "/bookmarks": "bookmarks",
  "/queue":     "queue",
  "/settings":  "settings",
  "/admin":     "admin",
};

const NO_SHELL = ["/login", "/pair"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState(false);

  const showShell = !NO_SHELL.some(p => pathname.startsWith(p)) && loadToken() !== null;

  useEffect(() => {
    if (showShell) {
      api.getMe().then(u => setIsAdmin(!!u.is_admin)).catch(() => {});
    }
  }, [showShell]);

  const currentPage = PATH_TO_PAGE[pathname] ?? "journals";

  const handleNavigate = (page: Page) => router.push(`/${page}`);
  const handleSignOut = () => { clearToken(); router.push("/login"); };

  if (!showShell) return <>{children}</>;

  return (
    <div style={{ display: "flex", minHeight: "100vh", width: "100%" }}>
      <Sidebar
        current={currentPage}
        onNavigate={handleNavigate}
        isAdmin={isAdmin}
        onSignOut={handleSignOut}
      />
      <main style={{ flex: 1, minWidth: 0, overflowY: "auto", background: "var(--color-surface, #fff)" }}>
        {children}
      </main>
    </div>
  );
}
