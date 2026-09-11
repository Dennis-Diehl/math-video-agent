import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import type { HistoryEntry } from "@/types";

function renderSidebar(overrides: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  return render(
    <Sidebar
      entries={[makeEntry()]}
      activeJobId={null}
      onNewProblem={vi.fn()}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      {...overrides}
    />,
  );
}

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
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("Solve x^2 - 4 = 0")).toBeInTheDocument();
    expect(screen.getByText("Integral...")).toBeInTheDocument();
  });

  it("calls onNewProblem when the new-problem button is clicked", async () => {
    const onNewProblem = vi.fn();
    render(<Sidebar entries={[]} activeJobId={null} onNewProblem={onNewProblem} onSelect={vi.fn()} onDelete={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /new problem/i }));

    expect(onNewProblem).toHaveBeenCalled();
  });

  it("calls onSelect with the job id when a history entry is clicked", async () => {
    const onSelect = vi.fn();
    render(
      <Sidebar entries={[makeEntry()]} activeJobId={null} onNewProblem={vi.fn()} onSelect={onSelect} onDelete={vi.fn()} />,
    );

    await userEvent.click(screen.getByText("Solve x^2 - 4 = 0"));

    expect(onSelect).toHaveBeenCalledWith("abc");
  });

  it("calls onSelect with the job id when a history entry is activated via keyboard", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Sidebar entries={[makeEntry()]} activeJobId={null} onNewProblem={vi.fn()} onSelect={onSelect} onDelete={vi.fn()} />,
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
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByTestId("history-entry-abc")).toHaveAttribute("data-unread", "true");
  });

  it("marks the active entry as selected", () => {
    render(
      <Sidebar entries={[makeEntry()]} activeJobId="abc" onNewProblem={vi.fn()} onSelect={vi.fn()} onDelete={vi.fn()} />,
    );

    expect(screen.getByTestId("history-entry-abc")).toHaveClass("Mui-selected");
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
          onDelete={vi.fn()}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
        />
      );
    }

    render(<ControlledSidebar />);

    // The history section stays mounted (so the width/opacity transition has something to
    // animate), but it's hidden from assistive tech and visually faded while collapsed.
    expect(screen.getByTestId("sidebar-history-section")).toHaveAttribute("aria-hidden", "true");

    await userEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));

    expect(screen.getByTestId("sidebar-history-section")).toHaveAttribute("aria-hidden", "false");
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
        onDelete={vi.fn()}
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));

    expect(onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it("renders as a permanent (in-flow) drawer on desktop", () => {
    render(
      <Sidebar
        entries={[makeEntry()]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        mobile={false}
      />,
    );

    // A permanent Drawer renders its content directly in flow, not inside a
    // Modal/portal, and is always present regardless of open/close state.
    expect(screen.getByText("Solve x^2 - 4 = 0")).toBeInTheDocument();
  });

  it("renders as a temporary overlay drawer on mobile that closes on backdrop click", async () => {
    const onCollapsedChange = vi.fn();
    render(
      <Sidebar
        entries={[makeEntry()]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
        mobile
      />,
    );

    expect(screen.getByText("Solve x^2 - 4 = 0")).toBeInTheDocument();

    const backdrop = document.querySelector(".MuiBackdrop-root");
    expect(backdrop).not.toBeNull();
    await userEvent.click(backdrop as Element);

    expect(onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it("does not render its content when the mobile drawer is collapsed (closed)", () => {
    render(
      <Sidebar
        entries={[makeEntry()]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        collapsed={true}
        onCollapsedChange={vi.fn()}
        mobile
      />,
    );

    expect(screen.queryByText("Solve x^2 - 4 = 0")).not.toBeInTheDocument();
  });

  it("makes the history section inert (not just aria-hidden) while collapsed, so it can't be tabbed into", async () => {
    function ControlledSidebar() {
      const [collapsed, setCollapsed] = useState(true);
      return (
        <Sidebar
          entries={[makeEntry()]}
          activeJobId={null}
          onNewProblem={vi.fn()}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
        />
      );
    }

    render(<ControlledSidebar />);

    // `aria-hidden` alone does not remove elements from the tab order — only
    // the native `inert` attribute does. jsdom (this project's version) doesn't
    // honor `inert` in its tab-order emulation, and doesn't reflect it as a
    // `.inert` DOM property either (`historySection.inert` reads back
    // `undefined` even with the attribute present) — so this asserts the
    // attribute directly rather than simulating Tab or reading the property.
    const historySection = screen.getByTestId("sidebar-history-section");
    expect(historySection).toHaveAttribute("inert");

    await userEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));

    expect(screen.getByTestId("sidebar-history-section")).not.toHaveAttribute("inert");
  });

  it("calls onDelete with the job id when the delete button is clicked", async () => {
    const onDelete = vi.fn();
    renderSidebar({ onDelete });

    await userEvent.click(screen.getByRole("button", { name: /delete solve x\^2 - 4 = 0/i }));

    expect(onDelete).toHaveBeenCalledWith("abc");
  });

  it("does not call onSelect when the delete button is clicked", async () => {
    const onSelect = vi.fn();
    renderSidebar({ onSelect });

    await userEvent.click(screen.getByRole("button", { name: /delete solve x\^2 - 4 = 0/i }));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("gives delete buttons a unique accessible name even when two entries share identical problem text", () => {
    render(
      <Sidebar
        entries={[
          makeEntry({ jobId: "job-one", problem: "Solve x^2 - 4 = 0" }),
          makeEntry({ jobId: "job-two", problem: "Solve x^2 - 4 = 0" }),
        ]}
        activeJobId={null}
        onNewProblem={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const deleteButtons = screen.getAllByRole("button", { name: /delete solve x\^2 - 4 = 0/i });
    expect(deleteButtons).toHaveLength(2);
    expect(deleteButtons[0]).toHaveAccessibleName(deleteButtons[0].getAttribute("aria-label")!);
    expect(deleteButtons[0].getAttribute("aria-label")).not.toBe(deleteButtons[1].getAttribute("aria-label"));
  });
});
