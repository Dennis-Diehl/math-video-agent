"use client";

import { useEffect } from "react";
import { jobWsUrl } from "@/lib/api";
import type { HistoryEntry, ProgressLine } from "@/types";

interface UseBackgroundJobWatcherOptions {
  entries: HistoryEntry[];
  activeJobId: string | null;
  onUpdate: (jobId: string, patch: Partial<HistoryEntry>) => void;
}

const NON_TERMINAL: HistoryEntry["status"][] = ["queued", "running"];

export function useBackgroundJobWatcher({
  entries,
  activeJobId,
  onUpdate,
}: UseBackgroundJobWatcherOptions): void {
  const watchIds = entries
    .filter((e) => NON_TERMINAL.includes(e.status) && e.jobId !== activeJobId)
    .map((e) => e.jobId)
    .join(",");

  useEffect(() => {
    if (!watchIds) return;
    const ids = watchIds.split(",");
    const sockets = ids.map((id) => {
      const socket = new WebSocket(jobWsUrl(id));
      socket.onmessage = (event) => {
        const line: ProgressLine = JSON.parse(event.data);
        if (line.node !== null) return;
        onUpdate(id, {
          status: line.status,
          video: line.video ?? undefined,
          detail: line.detail ?? undefined,
          unread: true,
        });
      };
      return socket;
    });
    return () => sockets.forEach((s) => s.close());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchIds]);
}
