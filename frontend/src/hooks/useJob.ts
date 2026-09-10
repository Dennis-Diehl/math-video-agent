"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createJob, jobWsUrl } from "@/lib/api";
import type { HistoryEntry, JobStatus, ProgressLine } from "@/types";

interface UseJobOptions {
  /** Fires on every state change so a caller (the history hook) can persist it without this hook knowing about localStorage. */
  onUpdate?: (jobId: string, patch: Partial<HistoryEntry>) => void;
}

export function useJob(options: UseJobOptions = {}) {
  const { onUpdate } = options;
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState<ProgressLine[]>([]);
  const [video, setVideo] = useState<string | undefined>(undefined);
  const [detail, setDetail] = useState<string | undefined>(undefined);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
    };
  }, []);

  const connect = useCallback(
    (id: string) => {
      socketRef.current?.close();
      const socket = new WebSocket(jobWsUrl(id));
      socketRef.current = socket;
      socket.onmessage = (event) => {
        const line: ProgressLine = JSON.parse(event.data);
        if (line.node !== null) {
          setProgress((prev) => [...prev, line]);
          return;
        }
        setStatus(line.status);
        if (line.status === "done" && line.video) setVideo(line.video);
        if (line.status === "error" && line.detail) setDetail(line.detail);
        onUpdate?.(id, {
          status: line.status,
          video: line.video ?? undefined,
          detail: line.detail ?? undefined,
        });
      };
    },
    [onUpdate],
  );

  const submit = useCallback(
    async (problem: string): Promise<string> => {
      const { job_id, queue_position } = await createJob(problem);
      setJobId(job_id);
      setStatus("queued");
      setProgress([]);
      setVideo(undefined);
      setDetail(undefined);
      onUpdate?.(job_id, {
        jobId: job_id,
        problem,
        submittedAt: Date.now(),
        status: "queued",
        queuePosition: queue_position,
        progress: [],
        unread: false,
      });
      connect(job_id);
      return job_id;
    },
    [connect, onUpdate],
  );

  /** Reattach to an existing job's websocket, e.g. when reopening a still-running chat. */
  const resume = useCallback(
    (id: string, existingProgress: ProgressLine[] = []) => {
      setJobId(id);
      setProgress(existingProgress);
      connect(id);
    },
    [connect],
  );

  const disconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  return { jobId, status, progress, video, detail, submit, resume, disconnect };
}
