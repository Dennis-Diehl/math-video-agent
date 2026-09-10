import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import * as api from "@/lib/api";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(public url: string) {}
  close(): void {}
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

describe("AppShell", () => {
  it("submitting a problem adds it to the sidebar history", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });

    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByTestId("history-entry-abc")).toBeInTheDocument();
  });

  it("shows progress for the newly submitted job right away, not just its sidebar entry", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });

    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    // The problem form must be gone and the problem's own text visible —
    // proof activeJobId actually points at the job that was just submitted,
    // not left null (see Task 13's plan-review note on this exact bug).
    // Scoped to the main content region: the same text also legitimately
    // appears in the sidebar's new history entry (Task 12's Sidebar renders
    // every entry's problem text verbatim), so an unscoped getByText would
    // find two matches once that entry is upserted into history.
    expect(screen.queryByLabelText(/problem/i)).not.toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByText("Solve x^2 - 4 = 0")).toBeInTheDocument();
  });

  it("clicking New problem shows an empty form again", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await userEvent.click(screen.getByRole("button", { name: /new problem/i }));

    expect(screen.getByLabelText(/problem/i)).toHaveValue("");
  });

  it("reopening a history entry checks the server and shows the reconciled result", async () => {
    vi.spyOn(api, "createJob").mockResolvedValue({ job_id: "abc", queue_position: 1 });
    vi.spyOn(api, "getJobStatus").mockResolvedValue({ status: "done", video: "abc/final.mp4" });
    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await userEvent.click(screen.getByRole("button", { name: /new problem/i }));

    await userEvent.click(await screen.findByTestId("history-entry-abc"));

    expect(api.getJobStatus).toHaveBeenCalledWith("abc");
    expect(await screen.findByTestId("video-player")).toBeInTheDocument();
  });

  it("disables the form while a submit is in flight, so a second click cannot double-submit", async () => {
    vi.spyOn(api, "createJob").mockReturnValue(new Promise<never>(() => {})); // never resolves

    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(screen.getByLabelText(/problem/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("shows an inline error and keeps the form when submitting fails (e.g. backend unreachable)", async () => {
    vi.spyOn(api, "createJob").mockRejectedValue(new Error("Failed to submit the problem (network error)."));

    render(<AppShell />);
    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to submit/i);
    // The form must still be there — a failed submit is not a crash, and
    // activeJobId must never have been set from a rejected submit().
    expect(screen.getByLabelText(/problem/i)).toBeInTheDocument();
  });
});
