"use client";

import { useState } from "react";
import { motion } from "framer-motion";
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
  // Surfaces a rejected getJobStatus reconciliation (e.g. backend unreachable)
  // when reopening a history entry. Kept separate from submitError: that state
  // is only rendered in the empty-state branch, but a reconciliation failure
  // happens with activeJobId already set (active-state branch), so it needs
  // its own slot to actually be visible.
  const [reconcileError, setReconcileError] = useState<string | null>(null);

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
    setReconcileError(null);
    setSubmitError(null);
    if (isMobile) setSidebarCollapsed(true);
  }

  async function handleSubmit(problem: string) {
    setSubmitError(null);
    setReconcileError(null);
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
      setReconcileError(null);
      setSubmitError(null);
    }
    history.remove(jobId);
  }

  async function handleSelect(jobId: string) {
    history.markRead(jobId);
    setActiveJobId(jobId);
    setReconcileError(null);
    if (isMobile) setSidebarCollapsed(true);

    let serverStatus;
    try {
      serverStatus = await getJobStatus(jobId);
    } catch (err) {
      // Keep activeJobId pointing at the clicked entry — its cached data (from
      // history) is still shown, just possibly stale, alongside this error,
      // rather than yanking the user back to the empty form and losing their
      // place over what may be a transient network/backend problem.
      setReconcileError(
        err instanceof Error ? err.message : "Could not check this job's status. Check your connection and try again.",
      );
      return;
    }
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
          {/* AnimatePresence (with an `exit` variant) was tried first, so the
              form could animate OUT as the active view animates in. It had to
              be dropped: AnimatePresence keeps the exiting element mounted
              until its exit animation's onComplete fires, which depends on
              real animation frames — jsdom/RTL's synchronous `userEvent`
              flow never advances real time far enough for that to fire, so in
              tests (and any consumer that doesn't wait ~300ms) BOTH the empty
              form and the active view were mounted at once, breaking every
              assertion that checks the form is gone right after submit. Without
              an `exit` prop, Framer Motion removes the outgoing element
              synchronously on unmount (no animation to wait for) — matching
              the prior CSS behavior exactly for the exit — while `initial`/
              `animate` still gives the incoming element a genuine animated
              entrance instead of an instant snap. This is the documented
              "simpler alternative" from the task spec, chosen because a
              shared `layoutId` morph between a centered form and a
              differently-shaped top-anchored echo box would not look good,
              and because true exit+enter overlap isn't test-observable here
              without changing how the whole suite drives time. */}
          {!activeJobId ? (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex flex-1 flex-col items-center justify-center"
            >
              {/* Centering within <main> centers relative to the space left of the
                  sidebar (only reserved at md+, it's an overlay below that), not the
                  full viewport — shift left by half the sidebar's current width so
                  this box lands at the true window center instead. */}
              <div
                className={`w-full max-w-3xl transition-[margin] duration-300 ${
                  sidebarCollapsed ? "md:ml-[-1.5rem]" : "md:ml-[-7.5rem]"
                }`}
              >
                <h1 className="mb-4 text-center text-xl font-semibold">What should I solve?</h1>
                {submitError && (
                  <div className="mb-4">
                    <ErrorMessage detail={submitError} />
                  </div>
                )}
                <ProblemForm onSubmit={handleSubmit} disabled={submitting} />
              </div>
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="mx-auto flex w-full max-w-3xl flex-col gap-4"
            >
              <p className="text-muted text-xs font-medium uppercase">Your task</p>
              <div className="bubble-system rounded-xl border border-[var(--border)] px-4 py-3 text-sm shadow-sm">
                {activeEntry?.problem ?? job.jobId}
              </div>
              {reconcileError && <ErrorMessage detail={reconcileError} />}
              {status && status !== "done" && status !== "error" && <JobProgress progress={progress} />}
              {status === "error" && detail && <ErrorMessage detail={detail} />}
              {status === "done" && video && (
                <>
                  <p className="text-muted text-xs font-medium uppercase">The solution</p>
                  <VideoPlayer src={video.startsWith("http") ? video : jobVideoUrl(activeJobId)} />
                </>
              )}
            </motion.div>
          )}
        </main>
      </div>
    </div>
  );
}
