import asyncio
import contextlib
import logging
import time

from pydantic import TypeAdapter, ValidationError

from graph.progress import ProgressLine
from jobs.sandbox import Sandbox, SandboxProcess
from jobs.store import JobStore

logger = logging.getLogger(__name__)

# Generous: several Gemini calls plus several Manim renders, one per scene.
CONTAINER_TIMEOUT_SECONDS = 600

CONCURRENT_JOBS = 1

# Shown to the user as the job's `detail`.
TIMEOUT_DETAIL = (
    f"This problem took longer than {CONTAINER_TIMEOUT_SECONDS // 60} minutes to "
    "process and was stopped. Try a simpler problem, or try again — this can "
    "happen if the AI service is temporarily slow."
)
INTERNAL_ERROR_DETAIL = "Something went wrong on our side while running this job."

_progress_line = TypeAdapter(ProgressLine)


def parse_line(raw: bytes) -> ProgressLine | None:
    """`None` for anything that isn't a progress line: warnings, bad UTF-8, other JSON."""
    try:
        return _progress_line.validate_json(raw)
    except ValidationError:
        return None


class Worker:
    """Takes jobs off a `JobStore`'s queue and runs each one in a `Sandbox`."""

    def __init__(
        self, store: JobStore, sandbox: Sandbox, timeout: float = CONTAINER_TIMEOUT_SECONDS
    ) -> None:
        self._store = store
        self._sandbox = sandbox
        self._timeout = timeout

    async def consume(self) -> None:
        """Runs forever; the catch-all keeps one bad job from stopping the queue."""
        while True:
            job_id, problem = await self._store.next_job()
            try:
                await self.run(job_id, problem)
            except Exception:
                logger.exception("Job %s crashed the worker", job_id)
                job = self._store.get(job_id)
                if job is not None and job.finished_at is None:
                    self._store.fail(job_id, INTERNAL_ERROR_DETAIL)

    async def run(self, job_id: str, problem: str) -> None:
        """Settles the job as done or error and never leaves a container behind."""
        started = time.monotonic()
        self._store.mark_running(job_id)
        logger.info("Job %s started", job_id)

        try:
            process = await self._sandbox.start(job_id, problem, self._store.output_dir(job_id))
        except OSError as e:
            logger.error("Job %s: sandbox did not start: %s", job_id, e)
            self._store.fail(job_id, f"Could not start the sandbox container: {e}")
            return

        try:
            async with asyncio.timeout(self._timeout):
                saw_result = await self._follow(job_id, process)
                await process.wait()
        except TimeoutError:
            await self._stop(job_id, process)
            self._store.fail(job_id, TIMEOUT_DETAIL)
        except BaseException:
            # Includes cancellation on shutdown.
            await self._stop(job_id, process)
            raise
        else:
            if not saw_result:
                self._store.fail(
                    job_id, f"The job stopped unexpectedly (exit code {process.returncode})."
                )

        job = self._store.get(job_id)
        logger.info(
            "Job %s finished: %s in %.1fs",
            job_id,
            job.status if job else "unknown",
            time.monotonic() - started,
        )

    async def _follow(self, job_id: str, process: SandboxProcess) -> bool:
        """Returns whether the terminal line arrived. Drains stdout to EOF so a
        full pipe can't block the container's exit."""
        assert process.stdout is not None
        saw_result = False
        while True:
            try:
                raw = await process.stdout.readline()
            except ValueError:
                continue  # longer than STREAM_LINE_LIMIT; the reader already dropped it
            if not raw:
                return saw_result
            line = parse_line(raw)
            if line is None or saw_result:
                continue
            if line["node"] is None:
                self._store.finish(job_id, line)
                saw_result = True
            else:
                self._store.record(job_id, line)

    async def _stop(self, job_id: str, process: SandboxProcess) -> None:
        with contextlib.suppress(OSError):
            await self._sandbox.stop(job_id)
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()


def start_workers(worker: Worker, count: int = CONCURRENT_JOBS) -> list["asyncio.Task[None]"]:
    return [asyncio.create_task(worker.consume()) for _ in range(count)]


async def stop_workers(tasks: list["asyncio.Task[None]"]) -> None:
    """Waits until each worker has stopped its container."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
