"use client";

import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import type { HistoryEntry } from "@/types";
import { ThemeToggle } from "./ThemeToggle";

interface SidebarProps {
  entries: HistoryEntry[];
  activeJobId: string | null;
  onNewProblem: () => void;
  onSelect: (jobId: string) => void;
  theme?: "dark" | "light";
  onToggleTheme?: () => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

export function Sidebar({
  entries,
  activeJobId,
  onNewProblem,
  onSelect,
  theme = "dark",
  onToggleTheme = () => {},
  collapsed = false,
  onCollapsedChange = () => {},
}: SidebarProps) {
  if (collapsed) {
    return (
      <div className="panel flex w-12 flex-col items-center gap-4 border-r py-3">
        <button aria-label="New problem" onClick={onNewProblem}>
          <Plus size={18} />
        </button>
        <button aria-label="Expand sidebar" onClick={() => onCollapsedChange(false)}>
          <ChevronRight size={18} />
        </button>
      </div>
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50 md:hidden"
        onClick={() => onCollapsedChange(true)}
        data-testid="sidebar-backdrop"
      />
      <div className="panel fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r md:static md:z-auto">
        <div className="border-b p-3">
          <button
            onClick={onNewProblem}
            className="btn-primary flex w-full items-center justify-center gap-2 rounded px-3 py-2"
          >
            <Plus size={16} />
            New problem
          </button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          <p className="text-muted mb-2 text-xs uppercase">History</p>
          <ul className="flex flex-col gap-2">
            {entries.map((entry) => (
              <li key={entry.jobId}>
                <button
                  type="button"
                  data-testid={`history-entry-${entry.jobId}`}
                  data-unread={entry.unread}
                  onClick={() => onSelect(entry.jobId)}
                  className={`bubble-system w-full cursor-pointer rounded p-2 text-left text-sm ${
                    entry.jobId === activeJobId ? "border-[var(--accent)]" : ""
                  } ${entry.unread ? "animate-pulse" : ""}`}
                >
                  {entry.problem}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex items-center justify-between border-t p-2">
          <button
            aria-label="Collapse sidebar"
            onClick={() => onCollapsedChange(true)}
            className="text-muted flex items-center gap-1 text-xs"
          >
            <ChevronLeft size={14} />
            Collapse
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </div>
    </>
  );
}
