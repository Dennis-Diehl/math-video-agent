"""In-memory job store and background runner. Single process, no Redis."""

import asyncio
import json
from pathlib import Path
from typing import Literal, TypedDict

from config.config import settings
from graph.progress import ProgressLine

SANDBOX_IMAGE = "math-video-agent-sandbox:latest"
CONTAINER_MEMORY_LIMIT = "2g"
CONTAINER_PIDS_LIMIT = "256"

# Generous: several Gemini calls plus several Manim renders, one per scene.
CONTAINER_TIMEOUT_SECONDS = 600

CONCURRENT_JOBS = 1

Status = Literal["queued", "running", "done", "error"]


class JobState(TypedDict):
    status: Status
    log: list[ProgressLine]
    video: str | None
    subscribers: list["asyncio.Queue[ProgressLine]"]


_jobs: dict[str, JobState] = {}

# Tracks submission order for queue_position(); asyncio.Queue can't be inspected.
_queue_order: list[str] = []
_pending: "asyncio.Queue[tuple[str, str]]" = asyncio.Queue()


def _output_dir(job_id: str) -> Path:
    return Path(settings.job_output_dir) / job_id


def submit(job_id: str, problem: str) -> int:
    """Register a new job and queue it. Returns its 1-based position in line."""
    _jobs[job_id] = {"status": "queued", "log": [], "video": None, "subscribers": []}
    _queue_order.append(job_id)
    _pending.put_nowait((job_id, problem))
    return len(_queue_order)


def queue_position(job_id: str) -> int | None:
    """1-based position among jobs still waiting, or `None` once it isn't."""
    try:
        return _queue_order.index(job_id) + 1
    except ValueError:
        return None


def get_status(job_id: str) -> dict[str, object] | None:
    """Snapshot for GET /jobs/{id}: status, live queue position, video once done."""
    job = _jobs.get(job_id)
    if job is None:
        return None

    result: dict[str, object] = {"status": job["status"]}
    if job["status"] == "queued":
        result["queue_position"] = queue_position(job_id)
    if job["video"]:
        result["video"] = job["video"]
    return result


def get_log(job_id: str) -> list[ProgressLine]:
    """Every line recorded for a job so far, in order."""
    return list(_jobs[job_id]["log"])


def subscribe(job_id: str) -> "asyncio.Queue[ProgressLine]":
    """Register for future lines. Call before get_log() to avoid a gap — a
    duplicate line is harmless, the frontend keys progress by node name."""
    queue: asyncio.Queue[ProgressLine] = asyncio.Queue()
    _jobs[job_id]["subscribers"].append(queue)
    return queue


def unsubscribe(job_id: str, queue: "asyncio.Queue[ProgressLine]") -> None:
    _jobs[job_id]["subscribers"].remove(queue)


def _record(job_id: str, line: ProgressLine) -> None:
    job = _jobs[job_id]
    job["log"].append(line)
    for queue in job["subscribers"]:
        queue.put_nowait(line)


async def _start_container(job_id: str, problem: str) -> "asyncio.subprocess.Process":
    """Start the sandbox container for one job (Docker-outside-of-Docker: talks
    to the host daemon via the mounted socket). Can raise OSError before the
    container starts — `_run` handles that separately from a mid-run failure.
    """
    output_dir = _output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    return await asyncio.create_subprocess_exec(
        "docker",
        "run",
        "--rm",
        "-e",
        f"PROBLEM={problem}",
        "-e",
        f"GEMINI_API_KEY={settings.gemini_api_key}",
        "-v",
        f"{output_dir.resolve()}:/output",
        "--memory",
        CONTAINER_MEMORY_LIMIT,
        "--pids-limit",
        CONTAINER_PIDS_LIMIT,
        SANDBOX_IMAGE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


def _fail(job_id: str, detail: str) -> None:
    """Record a job as failed for an infra reason — nothing ran, no node to blame."""
    error_line: ProgressLine = {"node": None, "status": "error", "detail": detail, "video": None}
    _record(job_id, error_line)
    _jobs[job_id]["status"] = "error"


async def _run(job_id: str, problem: str) -> None:
    """Run one job to completion. Must never raise — `_consume()`'s single
    background task loops over this; an uncaught exception kills it forever.
    """
    job = _jobs[job_id]
    job["status"] = "running"

    try:
        process = await _start_container(job_id, problem)
    except OSError as e:
        _fail(job_id, f"Could not start the sandbox container: {e}")
        return

    saw_result = False
    try:
        async with asyncio.timeout(CONTAINER_TIMEOUT_SECONDS):
            assert process.stdout is not None
            async for raw_line in process.stdout:
                text = raw_line.decode().strip()
                if not text:
                    continue
                try:
                    line: ProgressLine = json.loads(text)
                except json.JSONDecodeError:
                    continue  # third-party warning noise on stdout, not a progress line
                _record(job_id, line)
                if line["node"] is None:
                    saw_result = True
                    job["status"] = line["status"]
                    # Not line["video"]: that path is inside the removed container.
                    if line["status"] == "done":
                        job["video"] = str(_output_dir(job_id) / "final.mp4")
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()

    if not saw_result:
        _fail(job_id, f"The job stopped unexpectedly (exit code {process.returncode}).")


async def _consume() -> None:
    """Pull jobs off the queue forever, one at a time, running each to completion."""
    while True:
        job_id, problem = await _pending.get()
        _queue_order.remove(job_id)
        await _run(job_id, problem)
        _pending.task_done()


async def start_workers(count: int = CONCURRENT_JOBS) -> list["asyncio.Task[None]"]:
    """Start the background consumer tasks. Called once from `api/main.py`'s lifespan."""
    return [asyncio.create_task(_consume()) for _ in range(count)]
