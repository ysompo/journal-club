import { api } from "@jc/shared";

const TOKEN_KEY = "jc_access_token";
const USER_ID_KEY = "jc_user_id";
const API_URL_KEY = "jc_api_url";

// Resolve API URL: localStorage override → VITE_API_URL → fallback
const _builtIn = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
const _stored = localStorage.getItem(API_URL_KEY) ?? "";
const _resolvedUrl = (_stored || _builtIn || "http://localhost:8765").replace(/\/$/, "");
api.configure(_resolvedUrl);

const token = localStorage.getItem(TOKEN_KEY);
if (token) api.setToken(token);

export const needsServerSetup = !_stored && !_builtIn;

export function getApiUrl(): string {
  return _resolvedUrl;
}

export function saveApiUrl(url: string) {
  const clean = url.replace(/\/$/, "");
  localStorage.setItem(API_URL_KEY, clean);
  api.configure(clean);
}

export function loadStoredToken(): string | null {
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) api.setToken(t);
  return t;
}

export function saveToken(token: string, userId: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_ID_KEY, userId);
  api.setToken(token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_ID_KEY);
  api.setToken(null);
}

export function getStoredUserId(): string | null {
  return localStorage.getItem(USER_ID_KEY);
}
