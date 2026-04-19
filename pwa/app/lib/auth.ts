import { api } from "@jc/shared";

const TOKEN_KEY = "jc_access_token";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";

api.configure(API_URL);

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) api.setToken(t);
  return t;
}

export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  api.setToken(token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  api.setToken(null);
}

export function isAuthed(): boolean {
  return !!loadToken();
}
