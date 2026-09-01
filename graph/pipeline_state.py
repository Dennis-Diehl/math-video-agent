"""LangGraph pipeline state definition.

`PipelineState` is threaded through every node in the pipeline. Only
holds fields that currently-implemented nodes actually read or write.
"""

from typing import TypedDict

from config.schemas import Scene, Step


class PipelineState(TypedDict):
    """Shared state passed between pipeline nodes."""

    user_input: str
    problem_statement: str
    topic: str
    difficulty: str
    solution: list[Step]
    solvable: bool
    scenes: list[Scene]
    manim_codes: list[str]
    scene_videos: list[str]
    audio_files: list[str]
    scene_durations: list[float]
    final_video: str
    error: str | None
