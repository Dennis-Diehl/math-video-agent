import json

import pytest

from api import jobs


class FakeStream:
    """Stands in for `asyncio.subprocess.Process.stdout`: a fixed async iterator of lines."""

    def __init__(self, lines: list[str]):
        self._lines = iter(lines)

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._lines).encode()
        except StopIteration:
            raise StopAsyncIteration from None


class FakeProcess:
    """Stands in for `asyncio.subprocess.Process`: fixed stdout, a fixed exit code."""

    def __init__(self, lines: list[str], returncode: int = 0):
        self.stdout = FakeStream(lines)
        self.returncode = returncode

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def make_line(
    node: str | None, status: str = "done", detail: str | None = None, video: str | None = None
) -> str:
    return json.dumps({"node": node, "status": status, "detail": detail, "video": video}) + "\n"


@pytest.fixture(autouse=True)
def clean_job_state():
    # Module-level state — tests must reset it so jobs can't leak between tests.
    jobs._jobs.clear()
    jobs._queue_order.clear()
    yield
    jobs._jobs.clear()
    jobs._queue_order.clear()


def test_submit_registers_a_queued_job():
    position = jobs.submit("abc", "Solve x^2 - 4 = 0")

    assert position == 1
    assert jobs.get_status("abc") == {"status": "queued", "queue_position": 1}


def test_submit_increments_position_for_a_second_job():
    jobs.submit("first", "Solve x^2 - 4 = 0")
    position = jobs.submit("second", "Differentiate x**3")

    assert position == 2
    assert jobs.get_status("second") == {"status": "queued", "queue_position": 2}


def test_queue_position_recomputes_as_earlier_jobs_leave_the_queue():
    jobs.submit("first", "Solve x^2 - 4 = 0")
    jobs.submit("second", "Differentiate x**3")

    jobs._queue_order.remove("first")  # what a consumer task does on dequeue

    assert jobs.get_status("second") == {"status": "queued", "queue_position": 1}


def test_get_status_is_none_for_an_unknown_job():
    assert jobs.get_status("nonexistent") is None


def test_get_status_falls_back_to_disk_for_a_job_the_store_forgot(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.settings, "job_output_dir", str(tmp_path))
    video = tmp_path / "restarted" / "final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"fake video")

    assert jobs.get_status("restarted") == {"status": "done", "video": str(video)}


async def test_run_records_every_line_and_the_final_status(monkeypatch: pytest.MonkeyPatch):
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    process = FakeProcess(
        [
            make_line("classifier"),
            make_line("solver"),
            # Meaningless outside the container — api/jobs.py must not store this string.
            make_line(None, video="media/videos/x/final.mp4"),
        ]
    )

    async def fake_start_container(job_id: str, problem: str) -> FakeProcess:
        return process

    monkeypatch.setattr(jobs, "_start_container", fake_start_container)

    await jobs._run("abc", "Solve x^2 - 4 = 0")

    # The path api/jobs.py itself bind-mounted, not the container-internal one.
    expected_video = str(jobs._output_dir("abc") / "final.mp4")
    assert jobs.get_status("abc") == {"status": "done", "video": expected_video}
    assert [line["node"] for line in jobs.get_log("abc")] == ["classifier", "solver", None]


async def test_run_ignores_non_json_lines_from_third_party_warnings(
    monkeypatch: pytest.MonkeyPatch,
):
    # torch/huggingface_hub print warnings to stdout ahead of the JSON lines.
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    process = FakeProcess(
        [
            "Warning: You are sending unauthenticated requests to the HF Hub.\n",
            make_line("classifier"),
            make_line(None, video="media/videos/x/final.mp4"),
        ]
    )

    async def fake_start_container(job_id: str, problem: str) -> FakeProcess:
        return process

    monkeypatch.setattr(jobs, "_start_container", fake_start_container)

    await jobs._run("abc", "Solve x^2 - 4 = 0")

    assert [line["node"] for line in jobs.get_log("abc")] == ["classifier", None]
    status = jobs.get_status("abc")
    assert status is not None
    assert status["status"] == "done"


async def test_run_synthesizes_an_error_when_the_container_produces_no_result(
    monkeypatch: pytest.MonkeyPatch,
):
    # e.g. OOM-killed: some lines, never a node=None one.
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    process = FakeProcess([make_line("classifier")], returncode=137)

    async def fake_start_container(job_id: str, problem: str) -> FakeProcess:
        return process

    monkeypatch.setattr(jobs, "_start_container", fake_start_container)

    await jobs._run("abc", "Solve x^2 - 4 = 0")

    status = jobs.get_status("abc")
    assert status is not None
    assert status["status"] == "error"
    assert jobs.get_log("abc")[-1]["node"] is None


async def test_run_reports_an_error_when_the_container_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
):
    # e.g. `docker` missing or daemon unreachable — nothing ran, not even one line.
    jobs.submit("abc", "Solve x^2 - 4 = 0")

    async def fake_start_container(job_id: str, problem: str) -> FakeProcess:
        raise OSError("docker: command not found")

    monkeypatch.setattr(jobs, "_start_container", fake_start_container)

    await jobs._run("abc", "Solve x^2 - 4 = 0")

    status = jobs.get_status("abc")
    assert status is not None
    assert status["status"] == "error"
    assert jobs.get_log("abc")[-1]["node"] is None


async def test_subscribe_receives_lines_written_after_it_registers(
    monkeypatch: pytest.MonkeyPatch,
):
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    process = FakeProcess([make_line("classifier"), make_line(None, video="x.mp4")])

    async def fake_start_container(job_id: str, problem: str) -> FakeProcess:
        return process

    monkeypatch.setattr(jobs, "_start_container", fake_start_container)
    queue = jobs.subscribe("abc")

    await jobs._run("abc", "Solve x^2 - 4 = 0")

    first = await queue.get()
    second = await queue.get()
    assert first["node"] == "classifier"
    assert second["node"] is None
