import asyncio
import json
from pathlib import Path
from typing import Protocol

from config.config import settings

SANDBOX_IMAGE = "math-video-agent-sandbox:latest"
CONTAINER_MEMORY_LIMIT = "2g"
CONTAINER_PIDS_LIMIT = "256"
CONTAINER_CPU_LIMIT = "2"

# Longer stdout lines are skipped; progress lines are tiny.
STREAM_LINE_LIMIT = 1024 * 1024


class SandboxOutput(Protocol):
    async def readline(self) -> bytes: ...


class SandboxProcess(Protocol):
    """The slice of `asyncio.subprocess.Process` the worker uses."""

    @property
    def stdout(self) -> SandboxOutput | None: ...

    @property
    def returncode(self) -> int | None: ...

    async def wait(self) -> int: ...

    def kill(self) -> None:
        """Kills the local process only — for Docker the client, not the container."""


class Sandbox(Protocol):
    """Runs one job in isolation, printing `ProgressLine` JSON to stdout."""

    async def start(self, job_id: str, problem: str, output_dir: Path) -> SandboxProcess: ...

    async def stop(self, job_id: str) -> None: ...


def container_name(job_id: str) -> str:
    return f"math-video-job-{job_id}"


class DockerSandbox:
    """One throwaway container per job, run by the host daemon (DooD): the `-v`
    source is resolved on the host, so `job_output_dir` must be the same path there.

    Hardened, since it runs LLM-generated code:
    - problem and key via stdin — argv shows up in `ps`, env is inherited by Manim;
    - `--cap-drop ALL` keeps the non-dumpable pipeline process (`protect_memory()`)
      unreadable to its children;
    - `--name`, because killing the `docker run` client leaves the container running.
    """

    async def start(self, job_id: str, problem: str, output_dir: Path) -> SandboxProcess:
        """Raises OSError if `docker` itself can't be started."""
        output_dir.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--name",
            container_name(job_id),
            "--memory",
            CONTAINER_MEMORY_LIMIT,
            "--pids-limit",
            CONTAINER_PIDS_LIMIT,
            "--cpus",
            CONTAINER_CPU_LIMIT,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-v",
            f"{output_dir.resolve()}:/output",
            SANDBOX_IMAGE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=STREAM_LINE_LIMIT,
        )

        assert process.stdin is not None
        job = {"problem": problem, "gemini_api_key": settings.gemini_api_key}
        process.stdin.write(json.dumps(job).encode() + b"\n")
        await process.stdin.drain()
        process.stdin.close()
        return process

    async def stop(self, job_id: str) -> None:
        """Idempotent: an already exited container is not an error."""
        process = await asyncio.create_subprocess_exec(
            "docker",
            "kill",
            container_name(job_id),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
