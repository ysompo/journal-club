import type { Article, QueueItem, User, Journal, TocArticle, HistoryItem } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Auth token responses
export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

export interface QrTokenResponse {
  qr_token: string;
  expires_at: string;
}

// Article list response (may include tags and selected status)
export interface ArticleWithMeta extends Article {
  tags: string[];
  is_selected: boolean;
}

export interface ArticleListResponse {
  items: ArticleWithMeta[];
  total: number;
}

// Queue claim response
export interface ClaimResponse {
  item: QueueItem | null;
}

export class JournalClubApi {
  private token: string | null = null;

  // Called when a request that carried a bearer token comes back 401 — i.e. the
  // session itself is invalid/expired, not just a bad login/QR attempt. Wire this
  // up to clear stored credentials and send the user back to a login screen.
  onUnauthorized: (() => void) | null = null;

  constructor(public baseUrl: string) {}

  setToken(token: string | null) {
    this.token = token;
  }

  configure(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options: { blob?: boolean } = {}
  ): Promise<T> {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const hadToken = !!this.token;
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      let message = res.statusText;
      try {
        const err = await res.json();
        message = err.detail ?? message;
      } catch {}
      if (res.status === 401 && hadToken) {
        this.setToken(null);
        this.onUnauthorized?.();
        message = "Your session has expired — please sign in again.";
      }
      throw new ApiError(res.status, message);
    }

    if (options.blob) return res.blob() as unknown as T;
    if (res.status === 204) return undefined as unknown as T;
    return res.json();
  }

  // ── Auth ──────────────────────────────────────────────────────────────────

  register(hujiUsername: string, displayName: string, password: string, inviteCode?: string) {
    return this.request<TokenResponse>("POST", "/users/register", {
      huji_username: hujiUsername,
      display_name: displayName,
      password,
      ...(inviteCode ? { invite_code: inviteCode } : {}),
    });
  }

  login(hujiUsername: string, password: string) {
    return this.request<TokenResponse>("POST", "/users/login", {
      huji_username: hujiUsername,
      password,
    });
  }

  getMe() {
    return this.request<User>("GET", "/users/me");
  }

  generateQrToken() {
    return this.request<QrTokenResponse>("POST", "/users/qr-token");
  }

  pairTablet(qrToken: string, deviceLabel: string) {
    return this.request<TokenResponse>("POST", "/users/pair-tablet", {
      qr_token: qrToken,
      device_label: deviceLabel,
    });
  }

  // ── Articles ──────────────────────────────────────────────────────────────

  getArticles(params?: {
    q?: string;
    tag?: string;
    selected_only?: boolean;
    skip?: number;
    limit?: number;
  }) {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.tag) qs.set("tag", params.tag);
    if (params?.selected_only) qs.set("selected_only", "true");
    if (params?.skip != null) qs.set("skip", String(params.skip));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return this.request<ArticleListResponse>("GET", `/articles/${query ? `?${query}` : ""}`);
  }

  addArticle(input: string) {
    return this.request<ArticleWithMeta>("POST", "/articles/", { input });
  }

  uploadPdf(articleId: string, pdfBlob: Blob) {
    const formData = new FormData();
    formData.append("file", pdfBlob, `${articleId}.pdf`);
    const headers: Record<string, string> = {};
    const hadToken = !!this.token;
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    return fetch(`${this.baseUrl}/articles/${articleId}/pdf`, {
      method: "POST",
      headers,
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        let message = res.statusText;
        try { const e = await res.json(); message = e.detail ?? message; } catch {}
        if (res.status === 401 && hadToken) {
          this.setToken(null);
          this.onUnauthorized?.();
          message = "Your session has expired — please sign in again.";
        }
        throw new ApiError(res.status, message);
      }
      return res.json() as Promise<ArticleWithMeta>;
    });
  }

  getPdfUrl(articleId: string) {
    // Returns a URL string; caller fetches with auth header or uses this
    return `${this.baseUrl}/articles/${articleId}/pdf`;
  }

  async downloadPdf(articleId: string): Promise<Blob> {
    return this.request<Blob>("GET", `/articles/${articleId}/pdf`, undefined, { blob: true });
  }

  deleteArticle(articleId: string) {
    return this.request<void>("DELETE", `/articles/${articleId}`);
  }

  selectArticle(articleId: string) {
    return this.request<{ ok: boolean }>("POST", `/articles/${articleId}/select`);
  }

  deselectArticle(articleId: string) {
    return this.request<{ ok: boolean }>("DELETE", `/articles/${articleId}/select`);
  }

  updateTags(articleId: string, tags: string[]) {
    return this.request<{ tags: string[] }>("PUT", `/articles/${articleId}/tags`, { tags });
  }

  getTags() {
    return this.request<string[]>("GET", "/articles/tags");
  }

  emailArticles(articleIds: string[]) {
    return this.request<{ ok: boolean; sent_to: string[] }>("POST", "/articles/email", { article_ids: articleIds });
  }

  // ── Settings ──────────────────────────────────────────────────────────────

  getSettings() {
    return this.request<{ theme: string; font_size: string; email_addresses: string[] }>("GET", "/settings/");
  }

  updateSettings(patch: { theme?: string; font_size?: string; email_addresses?: string[] }) {
    return this.request<{ theme: string; font_size: string; email_addresses: string[] }>("PATCH", "/settings/", patch);
  }

  // ── Queue ─────────────────────────────────────────────────────────────────

  enqueue(input: string) {
    return this.request<QueueItem>("POST", "/queue/", { input });
  }

  getQueue(status?: QueueItem["status"]) {
    const qs = status ? `?status=${status}` : "";
    return this.request<QueueItem[]>("GET", `/queue/${qs}`);
  }

  claimQueueItem(itemId: string, deviceId: string) {
    return this.request<QueueItem>("POST", `/queue/${itemId}/claim`, { device_id: deviceId });
  }

  markDone(queueItemId: string, articleId: string) {
    return this.request<{ ok: boolean }>("POST", `/queue/${queueItemId}/done`, { article_id: articleId });
  }

  markFailed(queueItemId: string, error: string, errorStep?: string, publisher?: string) {
    return this.request<{ ok: boolean; retry_count: number }>("POST", `/queue/${queueItemId}/failed`, {
      error,
      error_step: errorStep ?? "",
      publisher: publisher ?? "",
    });
  }

  retryQueueItem(queueItemId: string) {
    return this.request<{ ok: boolean }>("POST", `/queue/${queueItemId}/retry`);
  }

  deleteQueueItem(queueItemId: string) {
    return this.request<{ ok: boolean }>("DELETE", `/queue/${queueItemId}`);
  }

  clearActiveQueue() {
    return this.request<{ ok: boolean }>("DELETE", `/queue/active`);
  }

  reportFailure(queueItemId: string) {
    return this.request<{ ok: boolean }>("POST", `/queue/${queueItemId}/report`);
  }

  // ── Admin ─────────────────────────────────────────────────────────────────

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getAdminUsers() { return this.request<any[]>("GET", "/admin/users"); }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getAdminReports(resolved = false) { return this.request<any[]>("GET", `/admin/reports${resolved ? "?resolved=true" : ""}`); }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getAdminStats() { return this.request<any>("GET", "/admin/stats"); }
  resolveReport(failureId: string) { return this.request<{ ok: boolean }>("POST", `/admin/reports/${failureId}/resolve`); }
  toggleAdmin(userId: string) { return this.request<{ is_admin: boolean }>("POST", `/admin/users/${userId}/toggle-admin`); }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createInvite(note?: string) { return this.request<any>("POST", "/admin/invites", { note: note ?? null }); }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  listInvites() { return this.request<any[]>("GET", "/admin/invites"); }
  deleteInvite(inviteId: string) { return this.request<{ ok: boolean }>("DELETE", `/admin/invites/${inviteId}`); }

  checkVersion() { return this.request<{ version: string; min_client_version: string }>("GET", "/version"); }

  // ── Journals ──────────────────────────────────────────────────────────────

  getJournals() {
    return this.request<Journal[]>("GET", "/journals/");
  }

  followJournal(journalId: string) {
    return this.request<{ ok: boolean }>("POST", `/journals/${journalId}/follow`);
  }

  unfollowJournal(journalId: string) {
    return this.request<{ ok: boolean }>("DELETE", `/journals/${journalId}/follow`);
  }

  getJournalToc(journalId: string, months = 1) {
    return this.request<TocArticle[]>("GET", `/journals/${journalId}/toc?months=${months}`);
  }

  addCustomJournal(fullName: string, abbreviation: string, issn: string) {
    return this.request<Journal>("POST", "/journals/custom", { full_name: fullName, abbreviation, issn });
  }

  // ── History ───────────────────────────────────────────────────────────────

  getHistory(limit = 50, offset = 0) {
    return this.request<HistoryItem[]>("GET", `/history/?limit=${limit}&offset=${offset}`);
  }

  addHistory(item: Omit<HistoryItem, "id" | "queued_at">) {
    return this.request<{ id: string; queued_at: string }>("POST", "/history/", item);
  }

  deleteHistory(itemId: string) {
    return this.request<{ ok: boolean }>("DELETE", `/history/${itemId}`);
  }

  // ── Users (extended) ──────────────────────────────────────────────────────

  changePassword(currentPassword: string, newPassword: string) {
    return this.request<{ ok: boolean }>("POST", "/users/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  // ── Devices ───────────────────────────────────────────────────────────────

  heartbeat() {
    return this.request<{ ok: boolean; timestamp: string }>("POST", "/devices/heartbeat");
  }

  desktopOnlineStatus() {
    return this.request<{ online: boolean; device_label: string | null; last_seen: string | null }>(
      "GET",
      "/devices/online"
    );
  }
}

// Default instance — consumers call setToken() and optionally override baseUrl
export const api = new JournalClubApi(
  typeof window !== "undefined"
    ? (window as unknown as { __JC_API_URL__?: string }).__JC_API_URL__ ?? "http://localhost:8765"
    : "http://localhost:8765"
);
