import { invoke } from "@tauri-apps/api/core";
import { useState, useEffect, useCallback } from "react";

export interface HujiCreds {
  email: string;
  password: string;
  chromeProfile: string;
  chromePath: string; // not stored in keychain — read from env or hardcoded
}

const EMPTY: HujiCreds = { email: "", password: "", chromeProfile: "", chromePath: "" };

export function useKeychain() {
  const [creds, setCreds] = useState<HujiCreds>(EMPTY);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    invoke<[string, string, string]>("get_huji_credentials")
      .then(([email, password, chromeProfile]) => {
        setCreds({ email, password, chromeProfile, chromePath: "" });
      })
      .catch(() => {
        // No keychain entry yet — first run
      })
      .finally(() => setLoaded(true));
  }, []);

  const save = useCallback(async (email: string, password: string, chromeProfile: string) => {
    await invoke("save_huji_credentials", { email, password, chromeProfile });
    setCreds((prev) => ({ ...prev, email, password, chromeProfile }));
  }, []);

  const clear = useCallback(async () => {
    await invoke("clear_huji_credentials");
    setCreds(EMPTY);
  }, []);

  return { creds, loaded, save, clear };
}
