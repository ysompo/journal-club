"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthed } from "./lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(isAuthed() ? "/archive" : "/login");
  }, [router]);
  return null;
}
