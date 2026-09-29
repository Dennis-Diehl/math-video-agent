import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import create_app
from api.routes.jobs import WS_CLOSE_UNKNOWN_JOB
from config.config import settings
from graph.progress import ProgressLine
from jobs.store import JobStore
from tests.job_fakes import FakeProcess

JOB_ID = "0123456789abcdef0123456789abcdef"
UNKNOWN_ID = "f" * 32
PROBLEM = "Solve x^2 - 4 = 0"


class BlockingSandbox:
    """Starts nothing and never returns, so a taken job stays `running` untouched."""

    async def start(self, job_id: str, problem: str, output_dir: Path) -> FakeProcess:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def stop(self, job_id: str) -> None:
        pass


@pytest.fixture(autouse=True)
def api_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "job_output_dir", str(tmp_path))


@pytest.fixture
def client() -> Iterator[TestClient]:
    # `with` runs the lifespan, which creates the store and starts the worker.
    with TestClient(create_app(sandbox=BlockingSandbox())) as test_client:
        yield test_client


def store_of(client: TestClient) -> JobStore:
    store: JobStore = client.app.state.store  # type: ignore[attr-defined]
    return store


def on_loop(client: TestClient, function, *args) -> None:  # type: ignore[no-untyped-def]
    """Call into the store on the app's event loop, where its asyncio queues live."""
    assert client.portal is not None
    client.portal.call(function, *args)


def line(node: str | None, status: str = "done", video: str | None = None) -> ProgressLine:
    return {"node": node, "status": status, "detail": None, "video": video}  # type: ignore[typeddict-item]


def test_health_returns_ok(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_fails_without_a_gemini_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"), TestClient(create_app()):
        pass


def test_cors_preflight_allows_the_frontend_origin(client: TestClient):
    response = client.options(
        "/api/v1/jobs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_create_job_accepts_and_points_at_the_status(client: TestClient):
    response = client.post("/api/v1/jobs", json={"problem": PROBLEM})

    assert response.status_code == 202
    body = response.json()
    assert len(body["job_id"]) == 32
    assert body["queue_position"] == 1
    assert response.headers["location"] == f"/api/v1/jobs/{body['job_id']}"


@pytest.mark.parametrize("problem", ["", "   ", "x" * (settings.max_problem_length + 1)])
def test_create_job_rejects_an_empty_or_oversized_problem(client: TestClient, problem: str):
    response = client.post("/api/v1/jobs", json={"problem": problem})

    assert response.status_code == 422


def test_create_job_is_503_once_the_queue_is_full(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_queued_jobs", 1)
    with TestClient(create_app(sandbox=BlockingSandbox())) as client:
        # Whether or not the worker has taken the first job yet, the third can't fit.
        responses = [client.post("/api/v1/jobs", json={"problem": PROBLEM}) for _ in range(3)]

    rejected = [r for r in responses if r.status_code == 503]
    assert rejected
    assert rejected[0].headers["retry-after"] == "60"


def test_job_status_is_404_for_an_unknown_job(client: TestClient):
    assert client.get(f"/api/v1/jobs/{UNKNOWN_ID}").status_code == 404


@pytest.mark.parametrize("job_id", ["nonexistent", "ABCDEF0123456789ABCDEF0123456789", "0" * 33])
def test_job_status_rejects_ids_the_api_never_issues(client: TestClient, job_id: str):
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 422


def test_job_status_reports_a_video_url_not_a_server_path(client: TestClient):
    store = store_of(client)
    on_loop(client, store.submit, JOB_ID, PROBLEM)
    on_loop(client, store.finish, JOB_ID, line(None, video="/inside/container.mp4"))

    response = client.get(f"/api/v1/jobs/{JOB_ID}")

    assert response.json() == {"status": "done", "video": f"/api/v1/jobs/{JOB_ID}/video"}


def test_job_video_is_404_before_the_video_exists(client: TestClient):
    on_loop(client, store_of(client).submit, JOB_ID, PROBLEM)

    assert client.get(f"/api/v1/jobs/{JOB_ID}/video").status_code == 404


def test_job_video_serves_the_file_once_done(client: TestClient):
    store = store_of(client)
    on_loop(client, store.submit, JOB_ID, PROBLEM)
    on_loop(client, store.finish, JOB_ID, line(None))
    video = store.video_path(JOB_ID)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake video")

    response = client.get(f"/api/v1/jobs/{JOB_ID}/video")

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"fake video"


def test_websocket_replays_a_finished_job_then_closes(client: TestClient):
    store = store_of(client)
    on_loop(client, store.submit, JOB_ID, PROBLEM)
    on_loop(client, store.record, JOB_ID, line("classifier"))
    on_loop(client, store.finish, JOB_ID, line(None))

    with client.websocket_connect(f"/api/v1/jobs/{JOB_ID}/ws") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()
        # The server used to wait forever here instead of closing.
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    assert first["node"] == "classifier"
    assert second == {
        "node": None,
        "status": "done",
        "detail": None,
        "video": f"/api/v1/jobs/{JOB_ID}/video",
    }


def test_websocket_streams_live_lines_until_the_result(client: TestClient):
    store = store_of(client)
    on_loop(client, store.submit, JOB_ID, PROBLEM)

    with client.websocket_connect(f"/api/v1/jobs/{JOB_ID}/ws") as websocket:
        wait_for(lambda: bool(store.get(JOB_ID).subscribers))  # type: ignore[union-attr]
        on_loop(client, store.record, JOB_ID, line("classifier"))
        on_loop(client, store.fail, JOB_ID, "boom")

        assert websocket.receive_json()["node"] == "classifier"
        assert websocket.receive_json()["detail"] == "boom"
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_websocket_serves_a_job_only_known_from_disk(client: TestClient):
    # Used to raise KeyError: the job exists on disk but not in memory.
    video = store_of(client).video_path(JOB_ID)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake video")

    with client.websocket_connect(f"/api/v1/jobs/{JOB_ID}/ws") as websocket:
        result = websocket.receive_json()
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    assert result["node"] is None
    assert result["video"] == f"/api/v1/jobs/{JOB_ID}/video"


def test_websocket_closes_immediately_for_an_unknown_job(client: TestClient):
    with (
        client.websocket_connect(f"/api/v1/jobs/{UNKNOWN_ID}/ws") as websocket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        websocket.receive_json()

    assert closed.value.code == WS_CLOSE_UNKNOWN_JOB


def test_websocket_unsubscribes_when_the_client_leaves_mid_job(client: TestClient):
    store = store_of(client)
    on_loop(client, store.submit, JOB_ID, PROBLEM)

    with client.websocket_connect(f"/api/v1/jobs/{JOB_ID}/ws"):
        wait_for(lambda: bool(store.get(JOB_ID).subscribers))  # type: ignore[union-attr]

    wait_for(lambda: not store.get(JOB_ID).subscribers)  # type: ignore[union-attr]


def wait_for(condition, timeout: float = 2) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.01)
