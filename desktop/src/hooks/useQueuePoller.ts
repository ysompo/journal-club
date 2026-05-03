import { useEffect, useRef, useCallback, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { api } from "@jc/shared";
import type { QueueItem } from "@jc/shared";
import { getStoredUserId, getApiUrl } from "../store/auth";
import type { HujiCreds } from "./useKeychain";

const POLL_INTERVAL_MS = 5_000;

export interface ActiveDownload {
  queueItemId: string;
  input: string;
  messages: string[];
  status: "downloading" | "done" | "error";
  errorMsg?: string;
}

interface Options {
  creds: HujiCreds;
  enabled: boolean;
  onArticleReady: () => void; // refresh archive list
}

const AUTH_ERROR_RE = /auth|login|password|credential|401|403|forbidden/i;

export function useQueuePoller({ creds, enabled, onArticleReady }: Options) {
  const [activeDownloads, setActiveDownloads] = useState<ActiveDownload[]>([]);
  const [queuedItems, setQueuedItems] = useState<QueueItem[]>([]);
  const [failedItems, setFailedItems] = useState<QueueItem[]>([]);
  const [needsReauth, setNeedsReauth] = useState(false);
  const [cloudflareAlert, setCloudflareAlert] = useState<{ queueItemId: string; message: string } | null>(null);
  const busyRef = useRef(false);
  const unlistenersRef = useRef<UnlistenFn[]>([]);
  // Items that failed in this session — never re-claim them even if the
  // backend re-queues them (overrides MAX_RETRIES > 0). Cleared on app restart.
  const failedThisSessionRef = useRef<Set<string>>(new Set());

  // Send heartbeat on mount + every 30s
  useEffect(() => {
    if (!enabled) return;
    const sendHB = () => api.heartbeat().catch(() => {});
    sendHB();
    const t = setInterval(sendHB, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [enabled]);

  const runSidecar = useCallback(
    async (item: QueueItem) => {
      const token = localStorage.getItem("jc_access_token") ?? "";
      const deviceId = getStoredUserId() ?? "unknown";

      // Register active download — replace any stale entry for the same item
      setActiveDownloads(prev => [
        ...prev.filter(d => d.queueItemId !== item.id),
        { queueItemId: item.id, input: item.input, messages: [], status: "downloading" },
      ]);

      // Listen to sidecar events for this download
      const addMsg = (msg: string) =>
        setActiveDownloads(prev =>
          prev.map(d =>
            d.queueItemId === item.id ? { ...d, messages: [...d.messages, msg] } : d
          )
        );

      // These unlisten functions are called as soon as this download finishes/errors
      // so they don't accumulate across multiple downloads in a session.
      let unlistenThisDownload: UnlistenFn[] = [];
      const cleanupListeners = () => {
        unlistenThisDownload.forEach(fn => fn());
        unlistenThisDownload = [];
      };

      const ul1 = await listen<string>(`download-progress-${item.id}`, ev => {
        try {
          const parsed = JSON.parse(ev.payload);
          if (parsed.type === "cloudflare_challenge") {
            setCloudflareAlert({ queueItemId: item.id, message: parsed.message });
            addMsg(parsed.message);
            return;
          }
          if (parsed.type === "progress") addMsg(parsed.message);
          if (parsed.type === "metadata") addMsg(`Found: ${parsed.article?.title ?? "article"}`);
          if (parsed.type === "done") {
            setActiveDownloads(prev =>
              prev.map(d => d.queueItemId === item.id ? { ...d, status: "done" } : d)
            );
            onArticleReady();
            cleanupListeners();
            // Remove after 3s
            setTimeout(() =>
              setActiveDownloads(prev => prev.filter(d => d.queueItemId !== item.id)),
              3000
            );
          }
          if (parsed.type === "error") {
            failedThisSessionRef.current.add(item.id);
            setActiveDownloads(prev =>
              prev.map(d =>
                d.queueItemId === item.id
                  ? { ...d, status: "error", errorMsg: parsed.message }
                  : d
              )
            );
            if (AUTH_ERROR_RE.test(parsed.message ?? "")) {
              setNeedsReauth(true);
            }
            cleanupListeners();
          }
        } catch {
          addMsg(ev.payload);
        }
      });

      const ul2 = await listen<string>(`download-stderr-${item.id}`, ev => {
        console.error("[sidecar stderr]", ev.payload);
        addMsg(`[err] ${ev.payload}`);
      });
      const ul3 = await listen<string>(`download-error-${item.id}`, ev => {
        console.error("[sidecar error]", ev.payload);
        failedThisSessionRef.current.add(item.id);
        setActiveDownloads(prev =>
          prev.map(d => d.queueItemId === item.id ? { ...d, status: "error", errorMsg: ev.payload } : d)
        );
        cleanupListeners();
      });
      unlistenThisDownload = [ul1, ul2, ul3];
      unlistenersRef.current.push(...unlistenThisDownload);

      try {
        await invoke("start_download", {
          cmd: {
            input: item.input,
            queue_item_id: item.id,
            device_id: deviceId,
            api_url: getApiUrl(),
            token,
            huji_email: creds.email,
            huji_password: creds.password,
            chrome_profile: creds.chromeProfile,
            chrome_path: creds.chromePath,
          },
        });
      } catch (e) {
        failedThisSessionRef.current.add(item.id);
        setActiveDownloads(prev =>
          prev.map(d =>
            d.queueItemId === item.id
              ? { ...d, status: "error", errorMsg: String(e) }
              : d
          )
        );
      }
    },
    [creds, onArticleReady]
  );

  const pollOnce = useCallback(async () => {
    if (busyRef.current || !enabled) return;

    // Fetch queued items
    let queued: QueueItem[];
    try {
      queued = await api.getQueue("queued");
    } catch {
      return;
    }

    // Refresh failed items on every poll
    try {
      const failed = await api.getQueue("failed");
      setFailedItems(failed);
    } catch {}

    // Skip items that already failed in this session — prevents auto-retry
    // even if the backend re-queued the item (e.g., MAX_RETRIES > 0 not yet
    // reloaded). User can still manually retry via the failed-items panel.
    const eligible = queued.filter(q => !failedThisSessionRef.current.has(q.id));
    setQueuedItems(eligible);

    if (eligible.length === 0) return;

    busyRef.current = true;
    try {
      // Process one at a time — claim then spawn sidecar
      const item = eligible[0];
      const deviceId = getStoredUserId() ?? "unknown";
      try {
        await api.claimQueueItem(item.id, deviceId);
      } catch {
        // Already claimed by another device — skip
        return;
      }
      // Remove from queued list now that it's being processed (it'll appear in activeDownloads)
      setQueuedItems(prev => prev.filter(q => q.id !== item.id));
      await runSidecar(item);
    } finally {
      busyRef.current = false;
    }
  }, [enabled, runSidecar]);

  // Poll on interval
  useEffect(() => {
    if (!enabled) return;
    pollOnce();
    const t = setInterval(pollOnce, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [enabled, pollOnce]);

  // On first enable: clear stale items left over from previous session
  const didClearRef = useRef(false);
  useEffect(() => {
    if (!enabled || didClearRef.current) return;
    didClearRef.current = true;
    api.clearActiveQueue().catch(() => {});
  }, [enabled]);

  // Load initial failed + queued items
  useEffect(() => {
    if (!enabled) return;
    api.getQueue("failed").then(setFailedItems).catch(() => {});
    api.getQueue("queued").then(setQueuedItems).catch(() => {});
  }, [enabled]);

  // Cleanup listeners on unmount
  useEffect(
    () => () => { unlistenersRef.current.forEach(fn => fn()); },
    []
  );

  const retry = useCallback(async (itemId: string) => {
    // User explicitly asked to retry — remove from session-fail blocklist
    failedThisSessionRef.current.delete(itemId);
    await api.retryQueueItem(itemId);
    setFailedItems(prev => prev.filter(i => i.id !== itemId));
    setTimeout(pollOnce, 500);
  }, [pollOnce]);

  const deleteItem = useCallback(async (itemId: string) => {
    await api.deleteQueueItem(itemId);
    setFailedItems(prev => prev.filter(i => i.id !== itemId));
  }, []);

  const cancelItem = useCallback(async (itemId: string) => {
    // Kill sidecar process if it's running for this item
    try { await invoke("cancel_download", { queueItemId: itemId }); } catch {}
    try { await api.deleteQueueItem(itemId); } catch {}
    setQueuedItems(prev => prev.filter(i => i.id !== itemId));
    setActiveDownloads(prev => prev.filter(d => d.queueItemId !== itemId));
  }, []);

  const report = useCallback(async (itemId: string) => {
    try {
      await api.reportFailure(itemId);
      // Tag the active download so the panel can show "Report sent"
      setActiveDownloads(prev =>
        prev.map(d =>
          d.queueItemId === itemId
            ? { ...d, errorMsg: (d.errorMsg ?? "") + "\n\n✓ Report sent" }
            : d
        )
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setActiveDownloads(prev =>
        prev.map(d =>
          d.queueItemId === itemId
            ? { ...d, errorMsg: (d.errorMsg ?? "") + `\n\n✗ Report failed: ${msg}` }
            : d
        )
      );
    }
  }, []);

  const clearReauth = useCallback(() => setNeedsReauth(false), []);
  const clearCloudflareAlert = useCallback(() => setCloudflareAlert(null), []);

  return {
    activeDownloads, queuedItems, failedItems,
    retry, deleteItem, cancelItem, report, pollOnce,
    needsReauth, clearReauth,
    cloudflareAlert, clearCloudflareAlert,
  };
}
