"use client";

import { useCallback, useEffect, useState } from "react";
import type { HistoryEntry } from "@/types";

const STORAGE_KEY = "math-video-agent:history";

function load(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function save(entries: HistoryEntry[]): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

export function useJobHistory() {
  const [entries, setEntries] = useState<HistoryEntry[]>(load);

  useEffect(() => save(entries), [entries]);

  const add = useCallback((entry: HistoryEntry) => {
    setEntries((prev) => [entry, ...prev]);
  }, []);

  const update = useCallback((jobId: string, patch: Partial<HistoryEntry>) => {
    setEntries((prev) => prev.map((e) => (e.jobId === jobId ? { ...e, ...patch } : e)));
  }, []);

  // Decides add-vs-update inside the setEntries updater (not from closed-over
  // `entries`) so two back-to-back calls for the same new jobId — e.g. submit()'s
  // synchronous onUpdate then the websocket's first message — can't both see
  // "not present" and add a duplicate entry.
  const upsert = useCallback((jobId: string, patch: Partial<HistoryEntry>) => {
    setEntries((prev) => {
      const exists = prev.some((e) => e.jobId === jobId);
      if (exists) {
        return prev.map((e) => (e.jobId === jobId ? { ...e, ...patch } : e));
      }
      // Add-path patches should always be a full HistoryEntry from useJob.submit()'s
      // first onUpdate; this guard flags a partial patch reaching here instead.
      if (process.env.NODE_ENV !== "production" && (!("problem" in patch) || !("submittedAt" in patch))) {
        console.error(`upsert: adding jobId ${jobId} without a full patch — this will produce a malformed entry`);
      }
      return [{ ...patch, jobId } as HistoryEntry, ...prev];
    });
  }, []);

  const remove = useCallback((jobId: string) => {
    setEntries((prev) => prev.filter((e) => e.jobId !== jobId));
  }, []);

  const clear = useCallback(() => setEntries([]), []);

  const markRead = useCallback((jobId: string) => {
    setEntries((prev) => prev.map((e) => (e.jobId === jobId ? { ...e, unread: false } : e)));
  }, []);

  return { entries, add, update, remove, clear, markRead, upsert };
}
