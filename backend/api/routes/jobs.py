import asyncio
import contextlib
import uuid
from typing import Annotated

import anyio
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.requests import HTTPConnection
from fastapi.responses import FileResponse

from api.schemas import JobRequest, JobStatus, JobSubmitted
from graph.progress import ProgressLine
from jobs.store import JobStore, QueueFullError

# Close code for "no such job"; 4000-4999 is reserved for applications.
WS_CLOSE_UNKNOWN_JOB = 4004

QUEUE_FULL_RETRY_AFTER_SECONDS = 60

router = APIRouter(prefix="/jobs", tags=["jobs"])

# uuid4().hex only: the id becomes a directory name.
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def get_store(connection: HTTPConnection) -> JobStore:
    store: JobStore = connection.app.state.store
    return store


Store = Annotated[JobStore, Depends(get_store)]


def _video_url(connection: HTTPConnection, job_id: str) -> str:
    return str(connection.app.url_path_for("job_video", job_id=job_id))


def _public_line(connection: HTTPConnection, job_id: str, line: ProgressLine) -> ProgressLine:
    """Swaps the server path for the video URL."""
    if line["video"] is None:
        return line
    return {**line, "video": _video_url(connection, job_id)}


@router.post(
    "",
    status_code=202,
    responses={503: {"description": "Too many jobs are already waiting."}},
)
async def create_job(
    body: JobRequest, store: Store, request: Request, response: Response
) -> JobSubmitted:
    """Queue a job. 202 with a `Location` header pointing at its status; 503 if the queue is full."""
    job_id = uuid.uuid4().hex
    try:
        position = store.submit(job_id, body.problem)
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail="Too many problems are waiting right now. Try again in a few minutes.",
            headers={"Retry-After": str(QUEUE_FULL_RETRY_AFTER_SECONDS)},
        ) from None
    response.headers["Location"] = str(request.app.url_path_for("job_status", job_id=job_id))
    return JobSubmitted(job_id=job_id, queue_position=position)


@router.get("/{job_id}", response_model_exclude_none=True)
async def job_status(job_id: JobId, store: Store, request: Request) -> JobStatus:
    """Current status snapshot; 404 for an id that is neither in memory nor on disk."""
    snapshot = store.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No job with that id.")
    return JobStatus(
        status=snapshot.status,
        queue_position=snapshot.queue_position,
        video=_video_url(request, job_id) if snapshot.video else None,
        detail=snapshot.detail,
    )


@router.get("/{job_id}/video", response_class=FileResponse)
async def job_video(job_id: JobId, store: Store) -> FileResponse:
    """Stream the finished MP4; 404 until the job has produced one."""
    snapshot = store.snapshot(job_id)
    if snapshot is None or snapshot.video is None or not snapshot.video.exists():
        raise HTTPException(status_code=404, detail="This job has no video yet.")
    return FileResponse(snapshot.video, media_type="video/mp4")


@router.websocket("/{job_id}/ws")
async def job_progress(websocket: WebSocket, job_id: JobId, store: Store) -> None:
    """Replays the log, then streams live until the terminal line."""
    await websocket.accept()

    if store.get(job_id) is None:
        snapshot = store.snapshot(job_id)
        if snapshot is None:
            await websocket.close(code=WS_CLOSE_UNKNOWN_JOB, reason="No job with that id.")
            return
        # Evicted or from before a restart: only the outcome survives.
        await websocket.send_json(
            {"node": None, "status": "done", "detail": None, "video": _video_url(websocket, job_id)}
        )
        await websocket.close()
        return

    # Subscribe before replaying the log — see JobStore.subscribe().
    queue = store.subscribe(job_id)
    finished = False
    try:
        # queue.get() alone never notices a client that left.
        async with anyio.create_task_group() as tasks:

            async def stream() -> None:
                nonlocal finished
                with contextlib.suppress(WebSocketDisconnect):
                    await _stream(websocket, job_id, store, queue)
                    finished = True
                tasks.cancel_scope.cancel()

            async def watch() -> None:
                await _wait_for_disconnect(websocket)
                tasks.cancel_scope.cancel()

            tasks.start_soon(stream)
            tasks.start_soon(watch)
    finally:
        store.unsubscribe(job_id, queue)

    if finished:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await websocket.close()


async def _stream(
    websocket: WebSocket,
    job_id: str,
    store: JobStore,
    queue: "asyncio.Queue[ProgressLine]",
) -> None:
    for line in store.log(job_id):
        await websocket.send_json(_public_line(websocket, job_id, line))
        if line["node"] is None:
            return
    while True:
        line = await queue.get()
        await websocket.send_json(_public_line(websocket, job_id, line))
        if line["node"] is None:
            return


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    try:
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
    except WebSocketDisconnect:
        pass
