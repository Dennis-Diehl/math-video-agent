"use client";

import { useCallback, useState } from "react";
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
import type { HistoryEntry } from "@/types";

export function AppShell() {
  const history = useJobHistory();
  const { theme, toggle } = useTheme();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const isMobile = useIsMobile();
  // Sidebar's collapsed state is lifted here (rather than kept as Sidebar-local
  // state) so selecting a history entry or starting a new problem can force it
  // closed on mobile — see handleSelect/handleNewProblem below. Initialized from
  // isMobile so a mobile load starts as a collapsed overlay while desktop/tablet
  // starts as a permanent expanded column, per the spec.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isMobile);

  // useJobHistory's `update` only patches an *existing* entry by jobId — it
  // never creates one. `useJob`'s onUpdate fires with a brand-new jobId the
  // very first time (right after submit), so history needs to add it then
  // and update it on every subsequent call. Upsert here rather than passing
  // `history.update` straight through, or the newly submitted job's sidebar
  // entry never appears.
  const handleJobUpdate = useCallback(
    (jobId: string, patch: Partial<HistoryEntry>) => {
      const exists = history.entries.some((e) => e.jobId === jobId);
      if (exists) {
        history.update(jobId, patch);
      } else {
        // Safe only because of a cross-file invariant: on the add-path, `patch`
        // always comes from useJob.submit()'s first onUpdate call, which sends a
        // complete HistoryEntry-shaped patch for a brand-new job; connect()'s
        // later partial patches (status/video/detail only) always target a jobId
        // already in history, so they never reach this branch. If useJob changes
        // what it sends here, this cast stops being sound.
        history.add({ ...patch, jobId } as HistoryEntry);
      }
    },
    [history],
  );

  const job = useJob({ onUpdate: handleJobUpdate });

  // Tracks which jobId the `job` hook currently owns live state for (i.e. it
  // was reached via submit()/resume(), so its websocket is — or was — the
  // authoritative source). `job.jobId` itself is unsuitable for this check:
  // useJob (Task 6) never clears it on disconnect(), so it stays set to the
  // last submitted/resumed id forever. Without a separately-owned flag,
  // reopening that same job id later (e.g. after the server has already
  // reported it "done") would still read `job.status`/`job.video` — stale
  // hook state nobody ever updated — instead of the freshly reconciled
  // history entry.
  const [liveJobId, setLiveJobId] = useState<string | null>(null);
  // Surfaced when `job.submit` rejects (e.g. the backend is unreachable) —
  // without this, a failed fetch is an unhandled promise rejection: no
  // crash, but no feedback either, and the form silently does nothing.
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Prevents a second click during the await window between clicking "Send"
  // and job.submit(problem) resolving — without this, a double-submit calls
  // job.submit() again, tearing down the first job's live connection mid-flight
  // (useJob.connect() closes the previous socket).
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
    <div className="flex h-screen">
      <Sidebar
        entries={history.entries}
        activeJobId={activeJobId}
        onNewProblem={handleNewProblem}
        onSelect={handleSelect}
        theme={theme}
        onToggleTheme={toggle}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />
      <main className="flex flex-1 flex-col gap-4 p-4">
        {!activeJobId ? (
          <>
            {submitError && <ErrorMessage detail={submitError} />}
            <ProblemForm onSubmit={handleSubmit} disabled={submitting} />
          </>
        ) : (
          <>
            <p className="font-medium">{activeEntry?.problem ?? job.jobId}</p>
            {status && status !== "done" && status !== "error" && <JobProgress progress={progress} />}
            {status === "error" && detail && <ErrorMessage detail={detail} />}
            {status === "done" && video && (
              <VideoPlayer src={video.startsWith("http") ? video : jobVideoUrl(activeJobId)} />
            )}
          </>
        )}
      </main>
    </div>
  );
}
