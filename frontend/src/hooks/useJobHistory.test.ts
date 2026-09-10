import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useJobHistory } from "./useJobHistory";
import type { HistoryEntry } from "@/types";

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    jobId: "abc",
    problem: "Solve x^2 - 4 = 0",
    submittedAt: 1000,
    status: "queued",
    progress: [],
    unread: false,
    ...overrides,
  };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("useJobHistory", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useJobHistory());
    expect(result.current.entries).toEqual([]);
  });

  it("adds an entry and persists it across a remount", () => {
    const { result, unmount } = renderHook(() => useJobHistory());

    act(() => result.current.add(makeEntry()));
    expect(result.current.entries).toHaveLength(1);

    unmount();
    const { result: remounted } = renderHook(() => useJobHistory());
    expect(remounted.current.entries).toEqual([makeEntry()]);
  });

  it("updates an existing entry by jobId", () => {
    const { result } = renderHook(() => useJobHistory());
    act(() => result.current.add(makeEntry()));

    act(() => result.current.update("abc", { status: "done", video: "x.mp4" }));

    expect(result.current.entries[0]).toMatchObject({ status: "done", video: "x.mp4" });
  });

  it("removes an entry", () => {
    const { result } = renderHook(() => useJobHistory());
    act(() => result.current.add(makeEntry()));

    act(() => result.current.remove("abc"));

    expect(result.current.entries).toEqual([]);
  });

  it("clears all entries", () => {
    const { result } = renderHook(() => useJobHistory());
    act(() => result.current.add(makeEntry()));
    act(() => result.current.add(makeEntry({ jobId: "def" })));

    act(() => result.current.clear());

    expect(result.current.entries).toEqual([]);
  });

  it("marks an entry read", () => {
    const { result } = renderHook(() => useJobHistory());
    act(() => result.current.add(makeEntry({ unread: true })));

    act(() => result.current.markRead("abc"));

    expect(result.current.entries[0].unread).toBe(false);
  });

  // Regression test for a real bug found during live e2e testing: the
  // submitted-problem echo showed the raw job UUID instead of the problem
  // text, and the sidebar showed an extra blank history entry for the same
  // job. Root cause was a stale-closure race in AppShell's old hand-rolled
  // add-vs-update check (`history.entries.some(...)`) — useJob.submit()
  // fires onUpdate synchronously with a complete patch (including
  // `problem`), then the websocket's first message fires onUpdate again with
  // a partial patch (no `problem`) before React commits the first state
  // update. Both calls saw the same stale, entry-less `entries` snapshot and
  // both took the "add" branch, creating a duplicate `problem`-less entry.
  // This can't invoke the deleted `handleJobUpdate` directly (it no longer
  // exists), but two synchronous calls in the same tick is a strictly
  // tighter race window than the original bug required, so passing this
  // proves `upsert` is correct even under the harder case.
  it("upserts a new jobId exactly once even when two calls land before a render commits", () => {
    const { result } = renderHook(() => useJobHistory());

    act(() => {
      result.current.upsert("job-1", {
        jobId: "job-1",
        problem: "Solve x^2 - 4 = 0",
        submittedAt: 1000,
        status: "queued",
        progress: [],
        unread: false,
      });
      // Second call, synchronously right after the first with no `await` or
      // re-render in between — this is the racy window. Partial patch, no
      // `problem`, matching what the websocket's progress-line handler sends.
      result.current.upsert("job-1", { status: "running" });
    });

    const matches = result.current.entries.filter((e) => e.jobId === "job-1");
    expect(matches).toHaveLength(1);
    expect(matches[0].problem).toBe("Solve x^2 - 4 = 0");
    expect(matches[0].status).toBe("running");
  });

  it("warns in dev when upsert adds a new jobId from a partial patch", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result } = renderHook(() => useJobHistory());

    act(() => result.current.upsert("job-2", { status: "running" }));

    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("job-2"));
  });
});
