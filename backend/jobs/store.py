import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from graph.progress import ProgressLine

Status = Literal["queued", "running", "done", "error"]

VIDEO_FILENAME = "final.mp4"


class QueueFullError(Exception):
    """Raised by `JobStore.submit()` when `max_queued` jobs are already waiting."""


@dataclass
class Job:
    """`video` is the host path, never the container's."""

    status: Status = "queued"
    log: list[ProgressLine] = field(default_factory=list)
    video: Path | None = None
    detail: str | None = None
    subscribers: list["asyncio.Queue[ProgressLine]"] = field(default_factory=list)
    finished_at: float | None = None


@dataclass(frozen=True)
class JobSnapshot:
    status: Status
    queue_position: int | None = None
    video: Path | None = None
    detail: str | None = None


class JobStore:
    """In-memory job state, queue and progress fan-out — one uvicorn worker only.

    Finished jobs are evicted after `ttl_seconds`; `snapshot()` then falls back to disk.
    """

    def __init__(
        self,
        output_root: Path,
        max_queued: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output_root = output_root
        self._max_queued = max_queued
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        # Tracks submission order for queue_position(); asyncio.Queue can't be inspected.
        self._queue_order: list[str] = []
        self._pending: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    def output_dir(self, job_id: str) -> Path:
        return self._output_root / job_id

    def video_path(self, job_id: str) -> Path:
        return self.output_dir(job_id) / VIDEO_FILENAME

    def submit(self, job_id: str, problem: str) -> int:
        """Returns the 1-based queue position; raises `QueueFullError` at `max_queued`."""
        self._evict_expired()
        if len(self._queue_order) >= self._max_queued:
            raise QueueFullError
        self._jobs[job_id] = Job()
        self._queue_order.append(job_id)
        self._pending.put_nowait((job_id, problem))
        return len(self._queue_order)

    async def next_job(self) -> tuple[str, str]:
        job_id, problem = await self._pending.get()
        self._queue_order.remove(job_id)
        return job_id, problem

    def queue_position(self, job_id: str) -> int | None:
        """1-based position among jobs still waiting, or `None` once it isn't."""
        try:
            return self._queue_order.index(job_id) + 1
        except ValueError:
            return None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def snapshot(self, job_id: str) -> JobSnapshot | None:
        """Falls back to disk for jobs evicted or lost on a restart."""
        job = self._jobs.get(job_id)
        if job is None:
            video = self.video_path(job_id)
            return JobSnapshot(status="done", video=video) if video.exists() else None

        return JobSnapshot(
            status=job.status,
            queue_position=self.queue_position(job_id) if job.status == "queued" else None,
            video=job.video,
            detail=job.detail,
        )

    def log(self, job_id: str) -> list[ProgressLine]:
        return list(self._jobs[job_id].log)

    def subscribe(self, job_id: str) -> "asyncio.Queue[ProgressLine]":
        """Register for future lines. Call before log() to avoid a gap — a
        duplicate line is harmless, the frontend keys progress by node name."""
        queue: asyncio.Queue[ProgressLine] = asyncio.Queue()
        self._jobs[job_id].subscribers.append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: "asyncio.Queue[ProgressLine]") -> None:
        """No-op if the job was evicted meanwhile."""
        job = self._jobs.get(job_id)
        if job is not None and queue in job.subscribers:
            job.subscribers.remove(queue)

    def record(self, job_id: str, line: ProgressLine) -> None:
        job = self._jobs[job_id]
        job.log.append(line)
        for queue in job.subscribers:
            queue.put_nowait(line)

    def mark_running(self, job_id: str) -> None:
        self._jobs[job_id].status = "running"

    def finish(self, job_id: str, line: ProgressLine) -> None:
        """Records the terminal line (`node=None`) and settles the outcome."""
        job = self._jobs[job_id]
        job.status = line["status"]
        job.detail = line["detail"]
        # Not line["video"]: that path is inside the removed container.
        job.video = self.video_path(job_id) if line["status"] == "done" else None
        job.finished_at = self._clock()
        self.record(job_id, {**line, "video": str(job.video) if job.video else None})

    def fail(self, job_id: str, detail: str) -> None:
        """Infra failure: no node to blame."""
        self.finish(job_id, {"node": None, "status": "error", "detail": detail, "video": None})

    def _evict_expired(self) -> None:
        """Keeps jobs a client is still streaming."""
        cutoff = self._clock() - self._ttl_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < cutoff and not job.subscribers
        ]
        for job_id in expired:
            del self._jobs[job_id]
