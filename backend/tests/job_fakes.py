import asyncio
import json
from pathlib import Path


def make_line(
    node: str | None, status: str = "done", detail: str | None = None, video: str | None = None
) -> bytes:
    return (
        json.dumps({"node": node, "status": status, "detail": detail, "video": video}) + "\n"
    ).encode()


class FakeOutput:
    """A fixed sequence of stdout lines. An `Exception` in the list is raised
    by the matching `readline()` call instead, like an overlong line would."""

    def __init__(self, lines: list[bytes | Exception]):
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        line = self._lines.pop(0)
        if isinstance(line, Exception):
            raise line
        return line


class HangingOutput:
    """Stdout that never produces a line, to trigger the worker's timeout."""

    async def readline(self) -> bytes:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class FakeProcess:
    """Stands in for `asyncio.subprocess.Process`: fixed stdout, a fixed exit code."""

    def __init__(self, lines: list[bytes | Exception], returncode: int = 0):
        self.stdout: FakeOutput | HangingOutput = FakeOutput(lines)
        self.returncode: int | None = returncode
        self.killed = False

    async def wait(self) -> int:
        assert self.returncode is not None
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class HangingProcess(FakeProcess):
    """A container that never prints and never exits on its own; only `kill()` ends it."""

    def __init__(self) -> None:
        super().__init__([])
        self.stdout = HangingOutput()
        self.returncode = None


class FakeSandbox:
    """Hands out prepared processes and records which containers were stopped."""

    def __init__(self, *processes: FakeProcess, error: OSError | None = None):
        self._processes = list(processes)
        self._error = error
        self.started: list[tuple[str, str]] = []
        self.stopped: list[str] = []

    async def start(self, job_id: str, problem: str, output_dir: Path) -> FakeProcess:
        self.started.append((job_id, problem))
        if self._error is not None:
            raise self._error
        return self._processes.pop(0)

    async def stop(self, job_id: str) -> None:
        self.stopped.append(job_id)
