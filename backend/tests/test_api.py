from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import jobs
from api.main import app


@pytest.fixture(autouse=True)
def clean_job_state():
    jobs._jobs.clear()
    jobs._queue_order.clear()
    yield
    jobs._jobs.clear()
    jobs._queue_order.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    # `with` runs the lifespan, which starts api/jobs.py's consumer task.
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_preflight_allows_the_frontend_origin(client: TestClient):
    response = client.options(
        "/jobs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_create_job_returns_a_job_id_and_position(client: TestClient):
    response = client.post("/jobs", json={"problem": "Solve x^2 - 4 = 0"})

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert body["queue_position"] == 1


def test_job_status_is_404_for_an_unknown_job(client: TestClient):
    response = client.get("/jobs/nonexistent")

    assert response.status_code == 404


def test_job_status_reads_back_the_in_memory_record(client: TestClient):
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    jobs._jobs["abc"]["status"] = "done"
    jobs._jobs["abc"]["video"] = "media/jobs/abc/final.mp4"

    response = client.get("/jobs/abc")

    assert response.json() == {"status": "done", "video": "media/jobs/abc/final.mp4"}


def test_job_video_is_404_before_the_video_exists(client: TestClient):
    jobs.submit("abc", "Solve x^2 - 4 = 0")

    response = client.get("/jobs/abc/video")

    assert response.status_code == 404


def test_websocket_replays_the_log_then_closes_on_the_result_line(client: TestClient):
    jobs.submit("abc", "Solve x^2 - 4 = 0")
    jobs._record("abc", {"node": "classifier", "status": "done", "detail": None, "video": None})
    jobs._record("abc", {"node": None, "status": "done", "detail": None, "video": "x.mp4"})

    with client.websocket_connect("/jobs/abc/ws") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert first["node"] == "classifier"
    assert second["node"] is None


def test_websocket_closes_immediately_for_an_unknown_job(client: TestClient):
    with (
        client.websocket_connect("/jobs/nonexistent/ws") as websocket,
        pytest.raises(WebSocketDisconnect),
    ):
        websocket.receive_json()
