from typing import Literal, TypedDict


class ProgressLine(TypedDict):
    """One stdout line. `node=None` marks the job's own outcome, not a node's."""

    node: str | None
    status: Literal["done", "error"]
    detail: str | None
    video: str | None
