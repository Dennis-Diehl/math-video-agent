import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import type { HistoryEntry } from "@/types";

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    jobId: "abc",
    problem: "Solve x^2 - 4 = 0",
    submittedAt: 1000,
    status: "done",
    progress: [],
    unread: false,
    ...overrides,
  };
}

describe("Sidebar", () => {
  it("lists every history entry by its problem text", () => {
    render(
      <Sidebar
        entries={[makeEntry({ jobId: "a" }), makeEntry({ jobId: "b", problem: "Integral..." })]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Solve x^2 - 4 = 0")).toBeInTheDocument();
    expect(screen.getByText("Integral...")).toBeInTheDocument();
  });

  it("calls onNewProblem when the new-problem button is clicked", async () => {
    const onNewProblem = vi.fn();
    render(<Sidebar entries={[]} activeJobId={null} onNewProblem={onNewProblem} onSelect={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /new problem/i }));

    expect(onNewProblem).toHaveBeenCalled();
  });

  it("calls onSelect with the job id when a history entry is clicked", async () => {
    const onSelect = vi.fn();
    render(
      <Sidebar entries={[makeEntry()]} activeJobId={null} onNewProblem={vi.fn()} onSelect={onSelect} />,
    );

    await userEvent.click(screen.getByText("Solve x^2 - 4 = 0"));

    expect(onSelect).toHaveBeenCalledWith("abc");
  });

  it("calls onSelect with the job id when a history entry is activated via keyboard", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Sidebar entries={[makeEntry()]} activeJobId={null} onNewProblem={vi.fn()} onSelect={onSelect} />,
    );

    screen.getByTestId("history-entry-abc").focus();
    await user.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledWith("abc");
  });

  it("marks an unread entry so it can be styled as pulsing", () => {
    render(
      <Sidebar
        entries={[makeEntry({ unread: true })]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId("history-entry-abc")).toHaveAttribute("data-unread", "true");
  });

  it("collapses to icon-only when collapsed is true, expands on toggle", async () => {
    function ControlledSidebar() {
      const [collapsed, setCollapsed] = useState(true);
      return (
        <Sidebar
          entries={[]}
          activeJobId={null}
          onNewProblem={vi.fn()}
          onSelect={vi.fn()}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
          theme="dark"
          onToggleTheme={vi.fn()}
        />
      );
    }

    render(<ControlledSidebar />);

    expect(screen.queryByText(/history/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));

    expect(screen.getByText(/history/i)).toBeInTheDocument();
  });

  it("calls onCollapsedChange(true) when the collapse button is clicked", async () => {
    const onCollapsedChange = vi.fn();
    render(
      <Sidebar
        entries={[]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
        theme="dark"
        onToggleTheme={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));

    expect(onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it("renders the expanded panel as a fixed overlay on mobile and static on desktop", () => {
    render(
      <Sidebar
        entries={[]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        collapsed={false}
        onCollapsedChange={vi.fn()}
      />,
    );

    const panel = screen.getByText(/history/i).closest("div.panel");
    expect(panel).toHaveClass("fixed", "inset-y-0", "left-0", "z-50", "md:static", "md:z-auto");
  });

  it("renders a backdrop when expanded that closes the sidebar on click", async () => {
    const onCollapsedChange = vi.fn();
    render(
      <Sidebar
        entries={[]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
      />,
    );

    const backdrop = screen.getByTestId("sidebar-backdrop");
    expect(backdrop).toHaveClass("fixed", "inset-0", "z-40", "md:hidden");

    await userEvent.click(backdrop);

    expect(onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it("does not render a backdrop when collapsed", () => {
    render(
      <Sidebar
        entries={[]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        collapsed={true}
        onCollapsedChange={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("sidebar-backdrop")).not.toBeInTheDocument();
  });

  it("renders the theme toggle when expanded", () => {
    render(
      <Sidebar
        entries={[]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        theme="dark"
        onToggleTheme={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /switch to light/i })).toBeInTheDocument();
  });
});
