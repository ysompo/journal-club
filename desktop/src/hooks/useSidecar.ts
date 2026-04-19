import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { useRef, useCallback } from "react";

export interface DownloadConfig {
  input: string;
  queue_item_id: string;
  device_id: string;
  api_url: string;
  token: string;
  huji_email: string;
  huji_password: string;
  chrome_profile: string;
  chrome_path: string;
}

export type SidecarEvent =
  | { type: "progress"; message: string }
  | { type: "metadata"; article: Record<string, unknown> }
  | { type: "done"; article_id: string }
  | { type: "error"; message: string; step: string };

interface UseSidecarOptions {
  onEvent: (event: SidecarEvent) => void;
}

export function useSidecar({ onEvent }: UseSidecarOptions) {
  const unlisteners = useRef<UnlistenFn[]>([]);

  const startDownload = useCallback(
    async (cmd: DownloadConfig) => {
      // Clean up any previous listeners
      for (const fn of unlisteners.current) fn();
      unlisteners.current = [];

      const unlistenProgress = await listen<string>("download-progress", (ev) => {
        try {
          const parsed = JSON.parse(ev.payload) as SidecarEvent;
          onEvent(parsed);
        } catch {
          onEvent({ type: "progress", message: ev.payload });
        }
      });

      const unlistenError = await listen<string>("download-error", (ev) => {
        onEvent({ type: "error", message: ev.payload, step: "process" });
      });

      unlisteners.current = [unlistenProgress, unlistenError];

      await invoke("start_download", { cmd });
    },
    [onEvent]
  );

  const cleanup = useCallback(() => {
    for (const fn of unlisteners.current) fn();
    unlisteners.current = [];
  }, []);

  return { startDownload, cleanup };
}
