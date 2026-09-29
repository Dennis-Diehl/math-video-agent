from typing import Annotated

from pydantic import BaseModel, StringConstraints

from config.config import settings
from jobs.store import Status

Problem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=settings.max_problem_length),
]


class JobRequest(BaseModel):
    """POST /jobs body. `problem` is stripped, non-empty and length-capped."""

    problem: Problem


class JobSubmitted(BaseModel):
    """POST /jobs response: the new job's id and its 1-based place in line."""

    job_id: str
    queue_position: int


class JobStatus(BaseModel):
    """GET /jobs/{id}. Fields that don't apply to the current status are omitted."""

    status: Status
    queue_position: int | None = None
    video: str | None = None  # URL path of GET /jobs/{id}/video, once done
    detail: str | None = None
