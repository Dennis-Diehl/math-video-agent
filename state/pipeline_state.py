"""LangGraph pipeline state definition.

`PipelineState` is threaded through every node in the pipeline. Only
holds fields that currently-implemented nodes actually read or write.
"""

from typing import TypedDict


class PipelineState(TypedDict):
    """Shared state passed between pipeline nodes."""

    user_input: str
    topic: str
    difficulty: str