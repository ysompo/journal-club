import { useEffect, useRef, useCallback, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { api } from "@jc/shared";
import type { QueueItem } from "@jc/shared";
import { getStoredUserId } from "../store/auth";
import type { HujiCreds } from "./useKeychain";

const POLL_INTERVAL_MS = 30_000;
const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8765";

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
  const [failedItems, setFailedItems] = useState<QueueItem[]>([]);
  const [needsReauth, setNeedsReauth] = useState(false);
  const busyRef = useRef(false);
  const unlistenersRef = useRef<UnlistenFn[]>([]);

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

      // Register active download
      setActiveDownloads(prev => [
        ...prev,
        { queueItemId: item.id, input: item.input, messages: [], status: "downloading" },
      ]);

      // Listen to sidecar events for this download
      const addMsg = (msg: string) =>
        setActiveDownloads(prev =>
          prev.map(d =>
            d.queueItemId === item.id ? { ...d, messages: [...d.messages, msg] } : d
          )
        );

      const ul1 = await listen<string>("download-progress", ev => {
        try {
          const parsed = JSON.parse(ev.payload);
          if (parsed.type === "progress") addMsg(parsed.message);
          if (parsed.type === "metadata") addMsg(`Found: ${parsed.article?.title ?? "article"}`);
          if (parsed.type === "done") {
            setActiveDownloads(prev =>
              prev.map(d => d.queueItemId === item.id ? { ...d, status: "done" } : d)
            );
            onArticleReady();
            // Remove after 3s
            setTimeout(() =>
              setActiveDownloads(prev => prev.filter(d => d.queueItemId !== item.id)),
              3000
            );
          }
          if (parsed.type === "error") {
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
          }
        } catch {
          addMsg(ev.payload);
        }
      });

      unlistenersRef.current.push(ul1);

      try {
        await invoke("start_download", {
          cmd: {
            input: item.input,
            queue_item_id: item.id,
            device_id: deviceId,
            api_url: API_URL,
            token,
            huji_email: creds.email,
            huji_password: creds.password,
            chrome_profile: creds.chromeProfile,
            chrome_path: creds.chromePath,
          },
        });
      } catch (e) {
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

    if (queued.length === 0) {
      // Also refresh failed items so UI stays current
      try {
        const failed = await api.getQueue("failed");
        setFailedItems(failed);
      } catch {}
      return;
    }

    busyRef.current = true;
    try {
      // Process one at a time — claim then spawn sidecar
      const item = queued[0];
      const deviceId = getStoredUserId() ?? "unknown";
      try {
        await api.claimQueueItem(item.id, deviceId);
      } catch {
        // Already claimed by another device — skip
        return;
      }
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

  // Load initial failed items
  useEffect(() => {
    if (!enabled) return;
    api.getQueue("failed").then(setFailedItems).catch(() => {});
  }, [enabled]);

  // Cleanup listeners on unmount
  useEffect(
    () => () => { unlistenersRef.current.forEach(fn => fn()); },
    []
  );

  const retry = useCallback(async (itemId: string) => {
    await api.retryQueueItem(itemId);
    setFailedItems(prev => prev.filter(i => i.id !== itemId));
    setTimeout(pollOnce, 500);
  }, [pollOnce]);

  const deleteItem = useCallback(async (itemId: string) => {
    await api.deleteQueueItem(itemId);
    setFailedItems(prev => prev.filter(i => i.id !== itemId));
  }, []);

  const report = useCallback(async (itemId: string) => {
    await api.reportFailure(itemId);
  }, []);

  const clearReauth = useCallback(() => setNeedsReauth(false), []);

  return { activeDownloads, failedItems, retry, deleteItem, report, pollOnce, needsReauth, clearReauth };
}
