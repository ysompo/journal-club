"use client";
import { LibraryPage } from "@jc/shared/components";
import { api } from "../lib/auth";

export default function Page() {
  return <LibraryPage api={api} />;
}
