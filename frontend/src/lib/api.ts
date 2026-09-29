import type { JobStatusSnapshot, JobSubmitted } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const JOBS_URL = `${API_URL}/api/v1/jobs`;

export async function createJob(problem: string): Promise<JobSubmitted> {
  const response = await fetch(JOBS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ problem }),
  });
  if (!response.ok) {
    throw new Error(
      (await readableDetail(response)) ?? `Failed to submit the problem (${response.status}).`,
    );
  }
  return response.json();
}

/** The backend's own message when it sent one (e.g. a full queue), else `null`. */
async function readableDetail(response: Response): Promise<string | null> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

export async function getJobStatus(jobId: string): Promise<JobStatusSnapshot | null> {
  const response = await fetch(`${JOBS_URL}/${jobId}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Failed to fetch job status (${response.status}).`);
  }
  return response.json();
}

export function jobVideoUrl(jobId: string): string {
  return `${JOBS_URL}/${jobId}/video`;
}

export function jobWsUrl(jobId: string): string {
  return `${JOBS_URL.replace(/^http/, "ws")}/${jobId}/ws`;
}
