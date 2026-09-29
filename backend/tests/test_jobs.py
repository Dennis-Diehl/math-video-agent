import asyncio
from pathlib import Path

import pytest

from jobs.store import JobStore, QueueFullError
from jobs.worker import TIMEOUT_DETAIL, Worker, parse_line, start_workers, stop_workers
from tests.job_fakes import FakeProcess, FakeSandbox, HangingProcess, make_line

PROBLEM = "Solve x^2 - 4 = 0"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(tmp_path: Path, clock: FakeClock) -> JobStore:
    return JobStore(output_root=tmp_path, max_queued=3, ttl_seconds=100, clock=clock)


# --- JobStore ---


def test_submit_registers_a_queued_job(store: JobStore):
    position = store.submit("abc", PROBLEM)

    snapshot = store.snapshot("abc")
    assert position == 1
    assert snapshot is not None
    assert snapshot.status == "queued"
    assert snapshot.queue_position == 1


def test_submit_increments_position_for_a_second_job(store: JobStore):
    store.submit("first", PROBLEM)

    assert store.submit("second", "Differentiate x**3") == 2


async def test_queue_position_recomputes_as_earlier_jobs_leave_the_queue(store: JobStore):
    store.submit("first", PROBLEM)
    store.submit("second", "Differentiate x**3")

    assert await store.next_job() == ("first", PROBLEM)

    snapshot = store.snapshot("second")
    assert snapshot is not None
    assert snapshot.queue_position == 1


def test_submit_rejects_jobs_once_the_queue_is_full(store: JobStore):
    for job_id in ("a", "b", "c"):
        store.submit(job_id, PROBLEM)

    with pytest.raises(QueueFullError):
        store.submit("d", PROBLEM)
    assert store.get("d") is None


def test_snapshot_is_none_for_an_unknown_job(store: JobStore):
    assert store.snapshot("nonexistent") is None


def test_snapshot_falls_back_to_disk_for_a_job_the_store_forgot(store: JobStore):
    video = store.video_path("restarted")
    video.parent.mkdir()
    video.write_bytes(b"fake video")

    snapshot = store.snapshot("restarted")

    assert snapshot is not None
    assert snapshot.status == "done"
    assert snapshot.video == video


def test_finish_stores_the_host_path_not_the_container_path(store: JobStore):
    store.submit("abc", PROBLEM)

    store.finish("abc", {"node": None, "status": "done", "detail": None, "video": "/tmp/x.mp4"})

    job = store.get("abc")
    assert job is not None
    assert job.video == store.video_path("abc")
    assert store.log("abc")[-1]["video"] == str(store.video_path("abc"))


def test_finished_jobs_are_evicted_after_their_ttl(store: JobStore, clock: FakeClock):
    store.submit("old", PROBLEM)
    store.fail("old", "boom")

    clock.now = 101
    store.submit("new", PROBLEM)

    assert store.get("old") is None
    assert store.get("new") is not None


def test_eviction_spares_unfinished_jobs_and_jobs_with_a_live_subscriber(
    store: JobStore, clock: FakeClock
):
    store.submit("waiting", PROBLEM)
    store.submit("watched", PROBLEM)
    store.fail("watched", "boom")
    store.subscribe("watched")

    clock.now = 1000
    store.submit("new", PROBLEM)

    assert store.get("waiting") is not None
    assert store.get("watched") is not None


def test_unsubscribe_tolerates_an_evicted_job(store: JobStore):
    store.submit("abc", PROBLEM)
    queue = store.subscribe("abc")
    store._jobs.clear()

    store.unsubscribe("abc", queue)  # must not raise


def test_subscribe_receives_lines_recorded_after_it_registers(store: JobStore):
    store.submit("abc", PROBLEM)
    queue = store.subscribe("abc")

    store.record("abc", {"node": "classifier", "status": "done", "detail": None, "video": None})

    assert queue.get_nowait()["node"] == "classifier"


# --- parse_line ---


@pytest.mark.parametrize(
    "raw",
    [
        b"Warning: You are sending unauthenticated requests to the HF Hub.\n",
        b"\n",
        b"123\n",  # valid JSON, not a progress line: used to kill the worker
        b'{"node": "x"}\n',
        b"\xff\xfe\n",  # invalid UTF-8
    ],
)
def test_parse_line_ignores_anything_that_is_not_a_progress_line(raw: bytes):
    assert parse_line(raw) is None


def test_parse_line_reads_a_progress_line():
    assert parse_line(make_line("solver")) == {
        "node": "solver",
        "status": "done",
        "detail": None,
        "video": None,
    }


# --- Worker ---


async def run(store: JobStore, sandbox: FakeSandbox, timeout: float = 5) -> None:
    store.submit("abc", PROBLEM)
    await store.next_job()
    await Worker(store, sandbox, timeout=timeout).run("abc", PROBLEM)


async def test_run_records_every_line_and_the_final_status(store: JobStore):
    process = FakeProcess(
        [make_line("classifier"), make_line("solver"), make_line(None, video="/tmp/x.mp4")]
    )

    await run(store, FakeSandbox(process))

    snapshot = store.snapshot("abc")
    assert snapshot is not None
    assert snapshot.status == "done"
    assert snapshot.video == store.video_path("abc")
    assert [line["node"] for line in store.log("abc")] == ["classifier", "solver", None]


async def test_run_skips_noise_and_overlong_lines(store: JobStore):
    process = FakeProcess(
        [
            b"Warning: noise\n",
            b"123\n",
            ValueError("Separator is not found, and chunk exceed the limit"),
            make_line("classifier"),
            make_line(None),
        ]
    )

    await run(store, FakeSandbox(process))

    assert [line["node"] for line in store.log("abc")] == ["classifier", None]


async def test_run_ignores_lines_after_the_result(store: JobStore):
    process = FakeProcess([make_line(None), make_line("late"), make_line(None, status="error")])

    await run(store, FakeSandbox(process))

    assert [line["node"] for line in store.log("abc")] == [None]
    job = store.get("abc")
    assert job is not None
    assert job.status == "done"


async def test_run_synthesizes_an_error_when_the_container_produces_no_result(
    store: JobStore,
):
    # e.g. OOM-killed: some lines, never a node=None one.
    await run(store, FakeSandbox(FakeProcess([make_line("classifier")], returncode=137)))

    snapshot = store.snapshot("abc")
    assert snapshot is not None
    assert snapshot.status == "error"
    assert "exit code 137" in (snapshot.detail or "")
    assert store.log("abc")[-1]["node"] is None


async def test_run_stops_the_container_and_reports_a_timeout(store: JobStore):
    process = HangingProcess()
    sandbox = FakeSandbox(process)

    await run(store, sandbox, timeout=0.05)

    snapshot = store.snapshot("abc")
    assert snapshot is not None
    assert snapshot.status == "error"
    assert snapshot.detail == TIMEOUT_DETAIL
    # Killing the `docker run` client alone would leave the container running.
    assert sandbox.stopped == ["abc"]
    assert process.killed
    assert len(store.log("abc")) == 1


async def test_run_reports_an_error_when_the_container_cannot_start(store: JobStore):
    await run(store, FakeSandbox(error=OSError("docker: command not found")))

    snapshot = store.snapshot("abc")
    assert snapshot is not None
    assert snapshot.status == "error"
    assert "docker: command not found" in (snapshot.detail or "")


async def test_consume_survives_a_job_that_crashes_the_worker(
    store: JobStore, monkeypatch: pytest.MonkeyPatch
):
    worker = Worker(store, FakeSandbox(FakeProcess([make_line(None)])))
    original_run = worker.run
    calls = 0

    async def crash_once(job_id: str, problem: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("unforeseen")
        await original_run(job_id, problem)

    monkeypatch.setattr(worker, "run", crash_once)
    store.submit("first", PROBLEM)
    store.submit("second", PROBLEM)

    task = asyncio.create_task(worker.consume())
    for _ in range(100):
        job = store.get("second")
        if job is not None and job.status == "done":
            break
        await asyncio.sleep(0.01)
    await stop_workers([task])

    first = store.get("first")
    second = store.get("second")
    assert first is not None and first.status == "error"
    assert second is not None and second.status == "done"


async def test_stop_workers_stops_the_running_container(store: JobStore):
    sandbox = FakeSandbox(HangingProcess())
    store.submit("abc", PROBLEM)
    tasks = start_workers(Worker(store, sandbox))
    for _ in range(100):
        if sandbox.started:
            break
        await asyncio.sleep(0.01)

    await stop_workers(tasks)

    assert sandbox.stopped == ["abc"]
    assert all(task.done() for task in tasks)
