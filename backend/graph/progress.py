"""Progress line shape, shared between the sandbox and the API.

Dependency-free so run_job.py (heavy) and api/jobs.py (light) can both
import it without pulling in the other's dependencies.
"""

from typing import Literal, TypedDict


class ProgressLine(TypedDict):
    """One stdout line. `node=None` marks the job's own outcome, not a node's."""

    node: str | None
    status: Literal["done", "error"]
    detail: str | None
    video: str | None
