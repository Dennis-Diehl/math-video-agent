"""FastAPI app: submit, poll, watch live, fetch the video. Thin — api/jobs.py
owns all state and the background work.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api import jobs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    workers = await jobs.start_workers()
    yield
    for worker in workers:
        worker.cancel()


app = FastAPI(lifespan=lifespan)


class JobRequest(BaseModel):
    problem: str


class JobSubmitted(BaseModel):
    job_id: str
    queue_position: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs")
def create_job(request: JobRequest) -> JobSubmitted:
    job_id = uuid.uuid4().hex
    position = jobs.submit(job_id, request.problem)
    return JobSubmitted(job_id=job_id, queue_position=position)


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    status = jobs.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No job with that id.")
    return status


@app.get("/jobs/{job_id}/video")
def job_video(job_id: str) -> FileResponse:
    status = jobs.get_status(job_id)
    video = status.get("video") if status else None
    if not video or not Path(str(video)).exists():
        raise HTTPException(status_code=404, detail="This job has no video yet.")
    return FileResponse(str(video), media_type="video/mp4")


@app.websocket("/jobs/{job_id}/ws")
async def job_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    if jobs.get_status(job_id) is None:
        await websocket.close(code=4004, reason="No job with that id.")
        return

    # Subscribe before replaying the log — see api/jobs.py's subscribe() docstring.
    queue = jobs.subscribe(job_id)
    try:
        for line in jobs.get_log(job_id):
            await websocket.send_json(line)
        while True:
            line = await queue.get()
            await websocket.send_json(line)
            if line["node"] is None:
                break
    except WebSocketDisconnect:
        pass
    finally:
        jobs.unsubscribe(job_id, queue)
