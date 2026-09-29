import { afterEach, describe, expect, it, vi } from "vitest";
import { createJob, getJobStatus, jobVideoUrl, jobWsUrl } from "./api";

describe("createJob", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the problem and returns the parsed job", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ job_id: "abc", queue_position: 1 }),
      }),
    );

    const result = await createJob("Solve x^2 - 4 = 0");

    expect(result).toEqual({ job_id: "abc", queue_position: 1 });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/jobs$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ problem: "Solve x^2 - 4 = 0" }),
      }),
    );
  });
});

describe("createJob errors", () => {
  afterEach(() => vi.restoreAllMocks());

  it("surfaces the backend's message, e.g. when the queue is full", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ detail: "Too many problems are waiting right now." }),
      }),
    );

    await expect(createJob("x")).rejects.toThrow("Too many problems are waiting right now.");
  });

  it("falls back to the status code when the body has no readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, json: () => Promise.reject(new Error()) }),
    );

    await expect(createJob("x")).rejects.toThrow("Failed to submit the problem (502).");
  });
});

describe("getJobStatus", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns null for a 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    expect(await getJobStatus("missing")).toBeNull();
  });

  it("returns the parsed status for a 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: "done" }) }),
    );

    expect(await getJobStatus("abc")).toEqual({ status: "done" });
  });
});

describe("URL builders", () => {
  it("build the video and websocket URLs from a job id", () => {
    expect(jobVideoUrl("abc")).toMatch(/\/api\/v1\/jobs\/abc\/video$/);
    expect(jobWsUrl("abc")).toMatch(/^ws/);
    expect(jobWsUrl("abc")).toMatch(/\/api\/v1\/jobs\/abc\/ws$/);
  });
});
