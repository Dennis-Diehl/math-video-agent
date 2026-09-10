export type JobStatus = "queued" | "running" | "done" | "error";

export interface JobSubmitted {
  job_id: string;
  queue_position: number;
}

export interface JobStatusSnapshot {
  status: JobStatus;
  queue_position?: number;
  video?: string;
  detail?: string;
}

export interface ProgressLine {
  node: string | null;
  status: "done" | "error";
  detail: string | null;
  video: string | null;
}

/** One entry in the browser's persisted chat history (localStorage). */
export interface HistoryEntry {
  jobId: string;
  problem: string;
  submittedAt: number;
  status: JobStatus;
  queuePosition?: number;
  video?: string;
  detail?: string;
  progress: ProgressLine[];
  unread: boolean;
}
