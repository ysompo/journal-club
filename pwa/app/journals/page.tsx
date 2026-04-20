"use client";
import { JournalsPage } from "@jc/shared/components";
import { api } from "../lib/auth";

export default function Page() {
  return <JournalsPage api={api} />;
}
