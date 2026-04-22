import { invoke } from "@tauri-apps/api/core";
import { useState, useEffect, useCallback } from "react";

export interface HujiCreds {
  email: string;
  password: string;
  chromeProfile: string;
  chromePath: string; // not stored in keychain — read from env or hardcoded
}

export interface AppCreds {
  username: string;
  password: string;
}

const EMPTY_HUJI: HujiCreds = { email: "", password: "", chromeProfile: "", chromePath: "" };
const EMPTY_APP: AppCreds = { username: "", password: "" };

export function useKeychain() {
  const [creds, setCreds] = useState<HujiCreds>(EMPTY_HUJI);
  const [appCreds, setAppCreds] = useState<AppCreds>(EMPTY_APP);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([
      invoke<[string, string, string]>("get_huji_credentials").catch(() => ["", "", ""] as [string, string, string]),
      invoke<[string, string]>("get_app_credentials").catch(() => ["", ""] as [string, string]),
    ]).then(([[email, password, chromeProfile], [username, appPassword]]) => {
      setCreds({ email, password, chromeProfile, chromePath: "" });
      setAppCreds({ username, password: appPassword });
    }).finally(() => setLoaded(true));
  }, []);

  const save = useCallback(async (email: string, password: string, chromeProfile: string) => {
    await invoke("save_huji_credentials", { email, password, chromeProfile });
    setCreds((prev) => ({ ...prev, email, password, chromeProfile }));
  }, []);

  const saveApp = useCallback(async (username: string, password: string) => {
    await invoke("save_app_credentials", { username, password });
    setAppCreds({ username, password });
  }, []);

  const clear = useCallback(async () => {
    await invoke("clear_huji_credentials");
    setCreds(EMPTY_HUJI);
  }, []);

  return { creds, appCreds, loaded, save, saveApp, clear };
}
