"use client";
import { QueuePage } from "@jc/shared/components";
import { api } from "../lib/auth";

export default function Page() {
  return <QueuePage api={api} />;
}
