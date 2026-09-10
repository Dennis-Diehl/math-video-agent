"use client";

import { useState } from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { ProblemForm } from "./ProblemForm";
import { JobProgress } from "./JobProgress";
import { VideoPlayer } from "./VideoPlayer";
import { ErrorMessage } from "./ErrorMessage";
import { useJobHistory } from "@/hooks/useJobHistory";
import { useJob } from "@/hooks/useJob";
import { useBackgroundJobWatcher } from "@/hooks/useBackgroundJobWatcher";
import { useTheme } from "@/hooks/useTheme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { getJobStatus, jobVideoUrl } from "@/lib/api";

export function AppShell() {
  const history = useJobHistory();
  const { theme, toggle } = useTheme();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const isMobile = useIsMobile();
  // Lifted here (not Sidebar-local) so handleSelect/handleNewProblem can force it
  // closed on mobile. Starts collapsed on mobile, expanded on desktop/tablet.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isMobile);

  // history.upsert (not .update) handles both add and patch: useJob's onUpdate
  // fires with a brand-new jobId on submit, then patches it on every message
  // after. upsert decides add-vs-update inside setEntries's updater so it can't
  // race two back-to-back calls into a duplicate entry (see useJobHistory).
  const job = useJob({ onUpdate: history.upsert });

  // Tracks which jobId `job` has live WS state for — `job.jobId` alone can't tell
  // (useJob never clears it on disconnect, so it just holds the last id forever).
  const [liveJobId, setLiveJobId] = useState<string | null>(null);
  // Surfaces a rejected job.submit (e.g. backend unreachable) instead of leaving
  // an unhandled promise rejection with no user feedback.
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Blocks a second click during the submit await — otherwise a double-submit
  // tears down the first job's live socket mid-flight (useJob.connect() closes it).
  const [submitting, setSubmitting] = useState(false);

  useBackgroundJobWatcher({
    entries: history.entries,
    activeJobId,
    onUpdate: history.update,
  });

  const activeEntry = history.entries.find((e) => e.jobId === activeJobId);

  function handleNewProblem() {
    job.disconnect();
    setLiveJobId(null);
    setActiveJobId(null);
    if (isMobile) setSidebarCollapsed(true);
  }

  async function handleSubmit(problem: string) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const newJobId = await job.submit(problem);
      setLiveJobId(newJobId);
      setActiveJobId(newJobId);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to submit the problem.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleDelete(jobId: string) {
    // Deleting the active entry would otherwise leave activeJobId pointing at a
    // removed entry, rendering the "job selected" pane with stale/undefined state.
    // Mirror handleNewProblem's cleanup to fall back to the empty-state form.
    if (jobId === activeJobId) {
      job.disconnect();
      setLiveJobId(null);
      setActiveJobId(null);
    }
    history.remove(jobId);
  }

  async function handleSelect(jobId: string) {
    history.markRead(jobId);
    setActiveJobId(jobId);
    if (isMobile) setSidebarCollapsed(true);

    const serverStatus = await getJobStatus(jobId);
    if (!serverStatus) return; // nothing to reconcile — keep the cached entry as-is

    if (serverStatus.status === "queued" || serverStatus.status === "running") {
      const entry = history.entries.find((e) => e.jobId === jobId);
      job.resume(jobId, entry?.progress ?? []);
      setLiveJobId(jobId);
      return;
    }

    // Server says the job is no longer live — the `job` hook isn't (and
    // shouldn't be) connected to it, so the reconciled history entry below
    // is now the source of truth for this id, not `job`'s own state.
    setLiveJobId(null);
    history.update(jobId, {
      status: serverStatus.status,
      video: serverStatus.video,
      detail: serverStatus.detail,
    });
  }

  const isLive = activeJobId !== null && activeJobId === liveJobId;
  const status = isLive ? job.status : activeEntry?.status;
  const progress = isLive ? job.progress : (activeEntry?.progress ?? []);
  const video = isLive ? job.video : activeEntry?.video;
  const detail = isLive ? job.detail : activeEntry?.detail;

  return (
    <div className="flex h-screen flex-col">
      <Header theme={theme} onToggleTheme={toggle} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          entries={history.entries}
          activeJobId={activeJobId}
          onNewProblem={handleNewProblem}
          onSelect={handleSelect}
          onDelete={handleDelete}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
        />
        <main className="flex flex-1 flex-col overflow-auto p-4">
          {!activeJobId ? (
            <div className="flex flex-1 flex-col items-center justify-center">
              <div className="w-full max-w-xl">
                <h1 className="mb-4 text-center text-xl font-semibold">What should I solve?</h1>
                {submitError && (
                  <div className="mb-4">
                    <ErrorMessage detail={submitError} />
                  </div>
                )}
                <ProblemForm onSubmit={handleSubmit} disabled={submitting} />
              </div>
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
              <div className="bubble-system rounded-xl border border-[var(--border)] px-4 py-3 text-sm shadow-sm">
                {activeEntry?.problem ?? job.jobId}
              </div>
              {status && status !== "done" && status !== "error" && <JobProgress progress={progress} />}
              {status === "error" && detail && <ErrorMessage detail={detail} />}
              {status === "done" && video && (
                <VideoPlayer src={video.startsWith("http") ? video : jobVideoUrl(activeJobId)} />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
