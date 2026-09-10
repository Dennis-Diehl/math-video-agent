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
  // True once the current socket has either delivered its terminal line or
  // been closed on purpose (disconnect()). Read inside onclose to tell an
  // unexpected drop (network blip, backend restart/crash — report an error)
  // apart from a deliberate close, which also fires onclose but must not.
  const closedExpectedlyRef = useRef(false);

  useEffect(() => {
    return () => {
      closedExpectedlyRef.current = true;
      socketRef.current?.close();
    };
  }, []);

  const connect = useCallback(
    (id: string) => {
      // Capture the outgoing socket and only close it AFTER socketRef.current
      // has already been repointed at the new socket below. That ordering is
      // what makes the identity check in the outgoing socket's onclose (see
      // below) correctly bail out regardless of whether close() fires
      // synchronously (test doubles) or asynchronously (a real WebSocket,
      // which always dispatches close as a later task) — by the time it
      // runs, socketRef.current is never the outgoing socket anymore.
      const previousSocket = socketRef.current;
      const socket = new WebSocket(jobWsUrl(id));
      socketRef.current = socket;
      closedExpectedlyRef.current = false;
      socket.onmessage = (event) => {
        const line: ProgressLine = JSON.parse(event.data);
        if (line.node !== null) {
          setProgress((prev) => [...prev, line]);
          return;
        }
        closedExpectedlyRef.current = true;
        setStatus(line.status);
        if (line.status === "done" && line.video) setVideo(line.video);
        if (line.status === "error" && line.detail) setDetail(line.detail);
        onUpdate?.(id, {
          status: line.status,
          video: line.video ?? undefined,
          detail: line.detail ?? undefined,
        });
      };
      socket.onerror = () => {
        // The close that follows a network-level error is what actually
        // drives the UI update (see onclose below) — this handler exists so
        // the error doesn't otherwise vanish as an unhandled/ignored event.
      };
      socket.onclose = () => {
        // This event may belong to a socket that's already been replaced by
        // a later connect() call — ignore it regardless of timing (see the
        // comment above on why socketRef.current is reassigned before the
        // outgoing socket is closed).
        if (socketRef.current !== socket) return;
        if (closedExpectedlyRef.current) return;
        closedExpectedlyRef.current = true;
        const errorDetail = "Connection to the server was lost. Reopen this problem to check its current status.";
        setStatus("error");
        setDetail(errorDetail);
        onUpdate?.(id, { status: "error", detail: errorDetail });
      };
      previousSocket?.close();
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
    closedExpectedlyRef.current = true;
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  return { jobId, status, progress, video, detail, submit, resume, disconnect };
}
