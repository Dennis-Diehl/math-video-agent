import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
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
});
