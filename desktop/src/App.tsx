import "./App.css";
import { useState, useEffect, useCallback } from "react";
import { LoginScreen } from "./components/LoginScreen";
import { ArchiveScreen } from "./components/ArchiveScreen";
import { HujiSetupScreen } from "./components/HujiSetupScreen";
import { ServerSetupScreen } from "./components/ServerSetupScreen";
import { DownloadPanel } from "./components/DownloadPanel";
import { HujiReauthModal } from "./components/HujiReauthModal";
import { loadStoredToken, clearToken, needsServerSetup } from "./store/auth";
import { useKeychain } from "./hooks/useKeychain";
import { useQueuePoller } from "./hooks/useQueuePoller";
import { api } from "@jc/shared";

const APP_VERSION = "0.1.0";

type AppState = "server-setup" | "loading" | "unauthenticated" | "needs-huji" | "authenticated";

function App() {
  const [appState, setAppState] = useState<AppState>(needsServerSetup ? "server-setup" : "loading");
  const [refreshKey, setRefreshKey] = useState(0);
  const [updateAvailable, setUpdateAvailable] = useState<string | null>(null);
  const { creds, loaded: keychainLoaded, save: saveCreds } = useKeychain();

  const onArticleReady = useCallback(() => setRefreshKey(k => k + 1), []);

  const { activeDownloads, failedItems, retry, deleteItem, report, needsReauth, clearReauth } = useQueuePoller({
    creds,
    enabled: appState === "authenticated",
    onArticleReady,
  });

  useEffect(() => {
    if (!keychainLoaded) return;
    const token = loadStoredToken();
    if (!token) {
      setAppState("unauthenticated");
    } else if (!creds.email || !creds.password) {
      setAppState("needs-huji");
    } else {
      setAppState("authenticated");
    }
  }, [keychainLoaded, creds.email, creds.password]);

  // Check for backend version update on startup
  useEffect(() => {
    if (appState !== "authenticated") return;
    api.checkVersion().then(res => {
      if (res.version !== APP_VERSION) setUpdateAvailable(res.version);
    }).catch(() => {});
  }, [appState]);

  if (appState === "server-setup") {
    return <ServerSetupScreen onConnected={() => setAppState("loading")} />;
  }

  if (appState === "loading") return null;

  if (appState === "unauthenticated") {
    return (
      <LoginScreen
        onSuccess={() =>
          setAppState(!creds.email || !creds.password ? "needs-huji" : "authenticated")
        }
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
        <div style={{ background: "var(--color-primary-fixed)", color: "var(--color-primary)", padding: "0.4rem 1.5rem", fontSize: "0.8rem", fontFamily: "var(--font-body)", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
          <span>A new version ({updateAvailable}) is available. Download the latest installer to update.</span>
          <button onClick={() => setUpdateAvailable(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-primary)", fontSize: "1rem", padding: "0 0.25rem" }}>×</button>
        </div>
      )}
      <ArchiveScreen
        onSignOut={() => { clearToken(); setAppState("unauthenticated"); }}
        hujiEmail={creds.email}
        hujiPassword={creds.password}
        chromeProfile={creds.chromeProfile}
        chromePath={creds.chromePath}
        refreshKey={refreshKey}
      />
      <DownloadPanel
        activeDownloads={activeDownloads}
        failedItems={failedItems}
        onRetry={retry}
        onDelete={deleteItem}
        onReport={report}
      />
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
