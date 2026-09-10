import type { JobStatusSnapshot, JobSubmitted } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function createJob(problem: string): Promise<JobSubmitted> {
  const response = await fetch(`${API_URL}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ problem }),
  });
  if (!response.ok) {
    throw new Error(`Failed to submit the problem (${response.status}).`);
  }
  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusSnapshot | null> {
  const response = await fetch(`${API_URL}/jobs/${jobId}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Failed to fetch job status (${response.status}).`);
  }
  return response.json();
}

export function jobVideoUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}/video`;
}

export function jobWsUrl(jobId: string): string {
  const wsBase = API_URL.replace(/^http/, "ws");
  return `${wsBase}/jobs/${jobId}/ws`;
}
