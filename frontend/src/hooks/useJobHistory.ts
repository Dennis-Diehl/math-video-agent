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

  const remove = useCallback((jobId: string) => {
    setEntries((prev) => prev.filter((e) => e.jobId !== jobId));
  }, []);

  const clear = useCallback(() => setEntries([]), []);

  const markRead = useCallback((jobId: string) => {
    setEntries((prev) => prev.map((e) => (e.jobId === jobId ? { ...e, unread: false } : e)));
  }, []);

  return { entries, add, update, remove, clear, markRead };
}
