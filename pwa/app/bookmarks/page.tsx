"use client";
import { BookmarksPage } from "@jc/shared/components";
import { api } from "../lib/auth";

export default function Page() {
  return <BookmarksPage api={api} />;
}
