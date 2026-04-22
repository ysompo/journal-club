import "./App.css";
import { useState, useEffect, useCallback } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { LoginScreen } from "./components/LoginScreen";
import { HujiSetupScreen } from "./components/HujiSetupScreen";
import { ServerSetupScreen } from "./components/ServerSetupScreen";
import { DownloadPanel } from "./components/DownloadPanel";
import { HujiReauthModal } from "./components/HujiReauthModal";
import { SettingsModal } from "./components/SettingsModal";
import { loadStoredToken, saveToken, clearToken, needsServerSetup } from "./store/auth";
import { useKeychain } from "./hooks/useKeychain";
import { useQueuePoller } from "./hooks/useQueuePoller";
import { api } from "@jc/shared";
import { Sidebar, JournalsPage, LibraryPage, BookmarksPage, QueuePage } from "@jc/shared/components";
import type { Page } from "@jc/shared/components";

type AppState = "server-setup" | "loading" | "unauthenticated" | "needs-huji" | "authenticated";

function UpdateBanner({ update, onDismiss }: { update: Update; onDismiss: () => void }) {
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInstall = async () => {
    setInstalling(true);
    setError(null);
    try {
      await update.downloadAndInstall();
      await relaunch();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setInstalling(false);
    }
  };

  return (
    <div style={{ background: "var(--color-primary-fixed)", color: "var(--color-primary)", padding: "0.4rem 1.5rem", fontSize: "0.8rem", fontFamily: "var(--font-body)", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
      <span>{error ? `Update failed: ${error}` : `Version ${update.version} is available.`}</span>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <button
          onClick={handleInstall}
          disabled={installing}
          style={{ background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", borderRadius: "4px", cursor: installing ? "default" : "pointer", fontSize: "0.8rem", padding: "0.2rem 0.75rem", opacity: installing ? 0.7 : 1 }}
        >
          {installing ? "Installing…" : "Install & Relaunch"}
        </button>
        {!installing && <button onClick={onDismiss} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-primary)", fontSize: "1rem", padding: "0 0.25rem" }}>×</button>}
      </div>
    </div>
  );
}

function App() {
  const [appState, setAppState] = useState<AppState>(needsServerSetup ? "server-setup" : "loading");
  const [currentPage, setCurrentPage] = useState<Page>("journals");
  const [showSettings, setShowSettings] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [updateAvailable, setUpdateAvailable] = useState<Update | null>(null);
  const { creds, appCreds, loaded: keychainLoaded, save: saveCreds, saveApp } = useKeychain();

  const onArticleReady = useCallback(() => setRefreshKey(k => k + 1), []);

  const { activeDownloads, failedItems, retry, deleteItem, report, needsReauth, clearReauth } = useQueuePoller({
    creds,
    enabled: appState === "authenticated",
    onArticleReady,
  });

  useEffect(() => {
    if (!keychainLoaded) return;

    const token = loadStoredToken();
    if (token) {
      // Valid session token still in localStorage
      setAppState(!creds.email || !creds.password ? "needs-huji" : "authenticated");
      return;
    }

    if (appCreds.username && appCreds.password) {
      // Auto-login with stored credentials
      api.login(appCreds.username, appCreds.password)
        .then(res => {
          saveToken(res.access_token, res.user_id);
          setAppState(!creds.email || !creds.password ? "needs-huji" : "authenticated");
        })
        .catch(() => {
          // Stored credentials no longer valid — show login screen
          setAppState("unauthenticated");
        });
    } else {
      setAppState("unauthenticated");
    }
  }, [keychainLoaded, appCreds.username, appCreds.password, creds.email, creds.password]);

  useEffect(() => {
    if (appState !== "authenticated") return;
    check().then(update => {
      if (update?.available) setUpdateAvailable(update);
    }).catch(() => {});
    api.getMe().then(u => setIsAdmin(!!u.is_admin)).catch(() => {});
  }, [appState]);

  const handleNavigate = (page: Page) => {
    if (page === "settings") { setShowSettings(true); return; }
    setCurrentPage(page);
  };

  const handleSignOut = () => { clearToken(); setAppState("unauthenticated"); };

  if (appState === "server-setup") {
    return <ServerSetupScreen onConnected={() => setAppState("loading")} />;
  }

  if (appState === "loading") return null;

  if (appState === "unauthenticated") {
    return (
      <LoginScreen
        onSuccess={(username, password) => {
          saveApp(username, password);
          setAppState(!creds.email || !creds.password ? "needs-huji" : "authenticated");
        }}
      />
    );
  }

  if (appState === "needs-huji") {
    return (
      <HujiSetupScreen
        onSave={async (email, password, chromeProfile) => {
          await saveCreds(email, password, chromeProfile);
          setAppState("authenticated");
        }}
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {updateAvailable && (
        <UpdateBanner update={updateAvailable} onDismiss={() => setUpdateAvailable(null)} />
      )}

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <Sidebar
          current={currentPage}
          onNavigate={handleNavigate}
          isAdmin={isAdmin}
          onSignOut={handleSignOut}
        />

        <main style={{ flex: 1, minWidth: 0, overflowY: "auto", background: "var(--color-surface, #fff)" }}>
          {currentPage === "journals" && <JournalsPage api={api} isDesktop />}
          {currentPage === "library" && <LibraryPage api={api} refreshKey={refreshKey} onSignOut={handleSignOut} />}
          {currentPage === "bookmarks" && <BookmarksPage api={api} />}
          {currentPage === "queue" && <QueuePage api={api} />}
          {currentPage === "admin" && <div style={{ padding: "1.5rem" }}><p style={{ color: "var(--color-on-surface-variant)" }}>Admin panel — use the web interface at your server URL.</p></div>}
        </main>
      </div>

      <DownloadPanel
        activeDownloads={activeDownloads}
        failedItems={failedItems}
        onRetry={retry}
        onDelete={deleteItem}
        onReport={report}
      />

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}

      {needsReauth && (
        <HujiReauthModal
          currentEmail={creds.email}
          currentChromeProfile={creds.chromeProfile}
          onSave={async (email, password, chromeProfile) => {
            await saveCreds(email, password, chromeProfile);
            clearReauth();
          }}
          onDismiss={clearReauth}
        />
      )}
    </div>
  );
}

export default App;
