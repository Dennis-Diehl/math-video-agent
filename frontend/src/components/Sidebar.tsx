"use client";

import { ChevronsLeft, ChevronsRight, Plus, X } from "lucide-react";
import type { HistoryEntry } from "@/types";

interface SidebarProps {
  entries: HistoryEntry[];
  activeJobId: string | null;
  onNewProblem: () => void;
  onSelect: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

export function Sidebar({
  entries,
  activeJobId,
  onNewProblem,
  onSelect,
  onDelete,
  collapsed = false,
  onCollapsedChange = () => {},
}: SidebarProps) {
  if (collapsed) {
    return (
      <div className="panel flex w-12 flex-col items-center gap-4 border-r py-3">
        <button aria-label="Expand sidebar" onClick={() => onCollapsedChange(false)}>
          <ChevronsRight size={18} />
        </button>
        <button aria-label="New problem" onClick={onNewProblem}>
          <Plus size={18} />
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
        <div className="flex flex-col gap-2 border-b p-3">
          <button
            aria-label="Collapse sidebar"
            onClick={() => onCollapsedChange(true)}
            className="text-muted self-end"
          >
            <ChevronsLeft size={18} />
          </button>
          <button
            onClick={onNewProblem}
            className="btn-primary flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 shadow-sm transition-colors"
          >
            <Plus size={16} />
            New problem
          </button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          <p className="text-muted mb-2 text-xs uppercase">History</p>
          <ul className="flex flex-col gap-2">
            {entries.map((entry) => (
              <li key={entry.jobId} className="group relative">
                <button
                  type="button"
                  data-testid={`history-entry-${entry.jobId}`}
                  data-unread={entry.unread}
                  onClick={() => onSelect(entry.jobId)}
                  className={`bubble-system w-full cursor-pointer rounded-xl border border-[var(--border)] p-2 pr-8 text-left text-sm shadow-sm transition-colors hover:border-[var(--fg-muted)] ${
                    entry.jobId === activeJobId ? "border-[var(--accent)]" : ""
                  } ${entry.unread ? "animate-pulse" : ""}`}
                >
                  {entry.problem}
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${entry.problem} (${entry.jobId.slice(0, 8)})`}
                  onClick={() => onDelete(entry.jobId)}
                  className="text-muted absolute right-2 top-1/2 -translate-y-1/2 opacity-100 transition-opacity hover:text-[var(--accent)] md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 md:focus-visible:opacity-100"
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
