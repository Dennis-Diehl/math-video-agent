"use client";

import { motion } from "framer-motion";
import { ChevronsLeft, Plus, X } from "lucide-react";
import type { HistoryEntry } from "@/types";

// Matches the sidebar's prior CSS widths (w-60 / w-12 in Tailwind's default
// rem scale: 15rem / 3rem at the 16px root the app uses).
const EXPANDED_WIDTH_PX = 240;
const COLLAPSED_WIDTH_PX = 48;

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
  return (
    <>
      {!collapsed && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => onCollapsedChange(true)}
          data-testid="sidebar-backdrop"
        />
      )}
      <motion.div
        animate={{ width: collapsed ? COLLAPSED_WIDTH_PX : EXPANDED_WIDTH_PX }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className={`panel flex flex-col overflow-hidden border-r md:static md:z-auto ${
          collapsed ? "" : "fixed inset-y-0 left-0 z-50"
        }`}
      >
        <div className={`flex flex-col gap-2 border-b p-3 ${collapsed ? "items-center" : ""}`}>
          <button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => onCollapsedChange(!collapsed)}
            className={`text-muted self-end rounded-full p-1 transition-colors duration-300 hover:bg-[var(--bg)] ${collapsed ? "self-center" : ""}`}
          >
            <motion.span
              className="inline-flex"
              animate={{ rotate: collapsed ? 180 : 0 }}
              transition={{ duration: 0.3, ease: "easeInOut" }}
            >
              <ChevronsLeft size={18} />
            </motion.span>
          </button>
          <button
            onClick={onNewProblem}
            className={`btn-primary flex items-center justify-center rounded-xl shadow-sm transition-all duration-300 hover:brightness-110 ${
              collapsed ? "p-2" : "w-full px-3 py-2"
            }`}
          >
            <Plus size={16} className="shrink-0" />
            <motion.span
              className="overflow-hidden whitespace-nowrap"
              animate={{
                opacity: collapsed ? 0 : 1,
                maxWidth: collapsed ? 0 : 160,
                marginLeft: collapsed ? 0 : 8,
              }}
              transition={{ duration: 0.3, ease: "easeInOut" }}
            >
              New problem
            </motion.span>
          </button>
        </div>
        <div
          data-testid="sidebar-history-section"
          aria-hidden={collapsed}
          inert={collapsed || undefined}
          className={`flex-1 overflow-auto p-3 transition-opacity duration-300 ease-in-out ${
            collapsed ? "opacity-0" : "opacity-100"
          }`}
        >
          <p className="text-muted mb-2 text-xs uppercase">History</p>
          <ul className="flex flex-col gap-2">
            {entries.map((entry) => (
              <li key={entry.jobId} className="group relative">
                <button
                  type="button"
                  data-testid={`history-entry-${entry.jobId}`}
                  data-unread={entry.unread}
                  onClick={() => onSelect(entry.jobId)}
                  className={`bubble-system w-full cursor-pointer rounded-xl border border-[var(--border)] p-2 pr-8 text-left text-sm shadow-sm transition-colors transition-[filter] hover:border-[var(--fg-muted)] hover:bg-[var(--fg-muted)]/10 hover:brightness-110 ${
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
      </motion.div>
    </>
  );
}
