"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import Fade from "@mui/material/Fade";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import { getTheme } from "@/lib/theme";
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
    <ThemeProvider theme={getTheme(theme)}>
      <CssBaseline />
      <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
        <Header theme={theme} onToggleTheme={toggle} />
        <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
          <Sidebar
            entries={history.entries}
            activeJobId={activeJobId}
            onNewProblem={handleNewProblem}
            onSelect={handleSelect}
            onDelete={handleDelete}
            collapsed={sidebarCollapsed}
            onCollapsedChange={setSidebarCollapsed}
            mobile={isMobile}
          />
          <Box component="main" sx={{ flex: 1, overflow: "auto", p: 3, display: "flex", flexDirection: "column" }}>
            {!activeJobId ? (
              <Fade in timeout={300}>
                <Box sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                  <Box sx={{ width: "100%", maxWidth: 640 }}>
                    <Typography variant="h6" align="center" sx={{ mb: 2 }}>
                      What should I solve?
                    </Typography>
                    {submitError && (
                      <Box sx={{ mb: 2 }}>
                        <ErrorMessage detail={submitError} />
                      </Box>
                    )}
                    <ProblemForm onSubmit={handleSubmit} disabled={submitting} />
                  </Box>
                </Box>
              </Fade>
            ) : (
              <Fade in timeout={300}>
                <Box sx={{ mx: "auto", width: "100%", maxWidth: 640, display: "flex", flexDirection: "column", gap: 2 }}>
                  <Typography variant="overline">Your task</Typography>
                  <Card variant="outlined">
                    <CardContent>{activeEntry?.problem ?? job.jobId}</CardContent>
                  </Card>
                  {reconcileError && <ErrorMessage detail={reconcileError} />}
                  {status && status !== "done" && status !== "error" && <JobProgress progress={progress} />}
                  {status === "error" && detail && <ErrorMessage detail={detail} />}
                  {status === "done" && video && (
                    <>
                      <Typography variant="overline">The solution</Typography>
                      <VideoPlayer src={video.startsWith("http") ? video : jobVideoUrl(activeJobId)} />
                    </>
                  )}
                </Box>
              </Fade>
            )}
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}
