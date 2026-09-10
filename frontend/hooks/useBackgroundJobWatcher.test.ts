import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useBackgroundJobWatcher } from "./useBackgroundJobWatcher";
import type { HistoryEntry } from "@/types";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close(): void {}
  emit(line: object): void {
    this.onmessage?.({ data: JSON.stringify(line) });
  }
}

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    jobId: "abc",
    problem: "Solve x^2 - 4 = 0",
    submittedAt: 1000,
    status: "running",
    progress: [],
    unread: false,
    ...overrides,
  };
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

describe("useBackgroundJobWatcher", () => {
  it("opens a socket for every non-terminal entry that isn't the active job", () => {
    const entries = [makeEntry({ jobId: "abc" }), makeEntry({ jobId: "def", status: "done" })];
    const onUpdate = vi.fn();

    renderHook(() => useBackgroundJobWatcher({ entries, activeJobId: null, onUpdate }));

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain("abc");
  });

  it("does not watch the currently active job", () => {
    const entries = [makeEntry({ jobId: "abc" })];

    renderHook(() => useBackgroundJobWatcher({ entries, activeJobId: "abc", onUpdate: vi.fn() }));

    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("marks the entry unread when its terminal line arrives", () => {
    const entries = [makeEntry({ jobId: "abc" })];
    const onUpdate = vi.fn();

    renderHook(() => useBackgroundJobWatcher({ entries, activeJobId: null, onUpdate }));
    const ws = FakeWebSocket.instances[0];

    act(() => ws.emit({ node: null, status: "done", detail: null, video: "x.mp4" }));

    expect(onUpdate).toHaveBeenCalledWith(
      "abc",
      expect.objectContaining({ status: "done", video: "x.mp4", unread: true }),
    );
  });
});
