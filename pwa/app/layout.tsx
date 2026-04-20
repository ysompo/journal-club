import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppShell } from "./components/AppShell";

export const metadata: Metadata = {
  title: "Journal Club",
  description: "Your personal academic library",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Journal Club" },
};

export const viewport: Viewport = {
  themeColor: "#005977",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      {/* Apply saved font size before first paint to avoid flash */}
      <script dangerouslySetInnerHTML={{ __html: `(function(){var s=localStorage.getItem('jc-font-size');var m={small:'14px',medium:'16px',large:'18px'};if(s&&m[s])document.documentElement.style.fontSize=m[s];})()` }} />
      <body className="min-h-full antialiased" style={{ display: "flex", minHeight: "100vh" }}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
