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

// Unlike FakeWebSocket above, this fires `close` asynchronously — matching a
// real WebSocket, whose close event always dispatches as a later task, never
// synchronously within the close() call itself. Used specifically to
// reproduce the reconnect-close race: the OLD socket's close event arriving
// only after a NEW socket already replaced it in socketRef.
class AsyncFakeWebSocket {
  static instances: AsyncFakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  url: string;
  closed = false;
  private pendingClose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    AsyncFakeWebSocket.instances.push(this);
  }

  send(): void {}
  close(): void {
    this.closed = true;
    // Defer, rather than invoke onclose synchronously — the fire is
    // triggered manually via fireClose() so the test controls exactly when
    // it lands relative to the next connect() call.
    this.pendingClose = () => this.onclose?.();
  }
  fireClose(): void {
    this.pendingClose?.();
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

  it("reports an error when the socket closes unexpectedly before a terminal line arrives", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const onUpdate = vi.fn();
    const { result } = renderHook(() => useJob({ onUpdate }));
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    const ws = FakeWebSocket.instances[0];

    // No terminal (node === null) line was ever emitted — this simulates a
    // dropped connection (network blip, backend restart/crash), not the
    // server finishing normally.
    act(() => ws.close());

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.detail).toMatch(/connection.*lost/i);
    expect(onUpdate).toHaveBeenCalledWith(
      "abc",
      expect.objectContaining({ status: "error", detail: expect.stringMatching(/connection.*lost/i) }),
    );
  });

  it("does not report an error when disconnect() is called deliberately (the intentional-close path)", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const { result } = renderHook(() => useJob());
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });

    act(() => {
      result.current.disconnect();
    });

    expect(FakeWebSocket.instances[0].closed).toBe(true);
    expect(result.current.status).toBe("queued"); // unchanged — no error reported
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

  it("ignores a stale close from the previous socket that lands asynchronously after a second submit (reconnect-close race)", async () => {
    AsyncFakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", AsyncFakeWebSocket);
    vi.spyOn(api, "createJob")
      .mockResolvedValueOnce({ job_id: "abc", queue_position: 1 })
      .mockResolvedValueOnce({ job_id: "def", queue_position: 1 });
    const onUpdate = vi.fn();

    const { result } = renderHook(() => useJob({ onUpdate }));
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    await act(async () => {
      await result.current.submit("Solve x^2 - 9 = 0");
    });

    expect(AsyncFakeWebSocket.instances).toHaveLength(2);
    const oldSocket = AsyncFakeWebSocket.instances[0];
    expect(oldSocket.closed).toBe(true);

    // The OLD socket's close event only fires now — well after the NEW
    // socket (for "def") is already current. It must be ignored: it must
    // NOT flip status to "error" for the new job, and must not report an
    // unexpected disconnect via onUpdate for "def".
    act(() => oldSocket.fireClose());

    expect(result.current.status).not.toBe("error");
    expect(result.current.jobId).toBe("def");
    expect(onUpdate).not.toHaveBeenCalledWith("def", expect.objectContaining({ status: "error" }));
  });

  it("ignores a stale close from the previous socket that lands asynchronously after resume follows submit (reconnect-close race)", async () => {
    AsyncFakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", AsyncFakeWebSocket);
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    const onUpdate = vi.fn();

    const { result } = renderHook(() => useJob({ onUpdate }));
    await act(async () => {
      await result.current.submit("Solve x^2 - 4 = 0");
    });
    act(() => {
      result.current.resume("xyz");
    });

    expect(AsyncFakeWebSocket.instances).toHaveLength(2);
    const oldSocket = AsyncFakeWebSocket.instances[0];
    expect(oldSocket.closed).toBe(true);

    act(() => oldSocket.fireClose());

    expect(result.current.status).not.toBe("error");
    expect(result.current.jobId).toBe("xyz");
    expect(onUpdate).not.toHaveBeenCalledWith("xyz", expect.objectContaining({ status: "error" }));
  });
});
