// Shared types used by desktop, PWA, and backend

export interface Article {
  id: string;
  title: string;
  authors: string[];
  journal: string;
  year: number;
  doi: string | null;
  url: string;
  abstract: string | null;
  pmid: string | null;
  volume: string | null;
  issue: string | null;
  pages: string | null;
  pub_date: string | null;
  keywords: string[];
  mesh_terms: string[];
  added_at: string;       // ISO timestamp
  pdf_size_bytes: number | null;
  pdf_on_server: boolean;
}

export interface Tag {
  id: string;
  name: string;
}

export interface SelectedArticle {
  article_id: string;
  tags: string[];
  starred_at: string;
}

export interface QueueItem {
  id: string;
  user_id: string;
  input: string;          // URL / PMID / DOI as entered
  status: "queued" | "claimed" | "downloading" | "done" | "failed";
  claimed_by: string | null;  // desktop device ID
  claimed_at: string | null;
  error: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface DownloadFailure {
  queue_item_id: string;
  article_id: string | null;
  error_step: string;
  error_message: string;
  publisher: string | null;
  occurred_at: string;
  reported: boolean;
}

export interface User {
  id: string;
  huji_username: string;
  display_name: string | null;
  created_at: string;
  last_active: string | null;
  storage_bytes_used: number;
  storage_limit_bytes: number;
}

export interface DevicePairing {
  id: string;
  user_id: string;
  device_label: string;   // "laptop", "home PC", "tablet"
  device_type: "desktop" | "tablet";
  last_seen: string;
  revoked: boolean;
}

export interface Settings {
  theme: "light" | "dark" | "system";
  font_size: "small" | "medium" | "large";
  email_addresses: string[];  // max 3
}
