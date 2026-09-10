import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useJob } from "./useJob";
import * as api from "@/lib/api";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  url: string;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(): void {}
  close(): void {
    this.closed = true;
    this.onclose?.();
  }
  emit(line: object): void {
    this.onmessage?.({ data: JSON.stringify(line) });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(() => vi.restoreAllMocks());

describe("useJob", () => {
  it("submits a problem and opens a websocket for it, resolving to the new job id", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });

    const { result } = renderHook(() => useJob());
    let returnedId: string | undefined;
    await act(async () => {
      returnedId = await result.current.submit("Solve x^2 - 4 = 0");
    });

    expect(returnedId).toBe("abc");
    expect(result.current.jobId).toBe("abc");
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain("abc");
  });

  it("accumulates progress lines and reports the terminal state as done", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const { result } = renderHook(() => useJob());
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    const ws = FakeWebSocket.instances[0];

    act(() => ws.emit({ node: "classifier", status: "done", detail: null, video: null }));
    expect(result.current.progress).toHaveLength(1);

    act(() => ws.emit({ node: null, status: "done", detail: null, video: "x.mp4" }));

    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.video).toBe("x.mp4");
  });

  it("reports the terminal state as error with detail", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const { result } = renderHook(() => useJob());
    await act(async () => {
      await result.current.submit("Unsolvable");
    });
    const ws = FakeWebSocket.instances[0];

    act(() => ws.emit({ node: null, status: "error", detail: "sympy could not solve this.", video: null }));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.detail).toBe("sympy could not solve this.");
  });

  it("calls onUpdate with every change so a caller can persist it", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const onUpdate = vi.fn();
    const { result } = renderHook(() => useJob({ onUpdate }));

    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });

    expect(onUpdate).toHaveBeenCalledWith(
      "abc",
      expect.objectContaining({ problem: "Solve x^2 - 4 = 0", status: "queued" }),
    );
  });

  it("closes the previous socket before opening a new one on a second submit", async () => {
    vi.spyOn(api, "createJob")
      .mockResolvedValueOnce({ job_id: "abc", queue_position: 1 })
      .mockResolvedValueOnce({ job_id: "def", queue_position: 1 });

    const { result } = renderHook(() => useJob());
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    await act(async () => {
      await result.current.submit("Solve x^2 - 9 = 0");
    });

    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[0].closed).toBe(true);
    expect(FakeWebSocket.instances[1].closed).toBe(false);
  });

  it("closes the previous socket before opening a new one when resume follows submit", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });

    const { result } = renderHook(() => useJob());
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    act(() => {
      result.current.resume("xyz");
    });

    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[0].closed).toBe(true);
    expect(FakeWebSocket.instances[1].closed).toBe(false);
  });
});
