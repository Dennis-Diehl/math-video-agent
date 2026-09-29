from typing import Literal

# pydantic validates these (jobs/worker.py) and needs this TypedDict on Python < 3.12.
from typing_extensions import TypedDict


class ProgressLine(TypedDict):
    """One stdout line. `node=None` marks the job's own outcome, not a node's."""

    node: str | None
    status: Literal["done", "error"]
    detail: str | None
    video: str | None
