"""Pydantic schemas shared across pipeline nodes.

These are the structured-output contracts that `BaseLLM.generate_structured`
validates LLM responses against.
"""

from typing import Literal

from pydantic import BaseModel


class Classification(BaseModel):
    """Topic, difficulty and cleaned-up wording of a math problem."""

    topic: Literal[
        "algebra", "geometry", "trigonometry", "calculus", "linear_algebra", "probability"
    ]
    difficulty: Literal["school", "university"]
    problem_statement: str


class Extraction(BaseModel):
    """A sympy code snippet extracted from a natural-language math problem."""

    sympy_code: str


class Step(BaseModel):
    """One step of a solution, with narration text and its mathematical expression."""

    explanation: str
    expression: str


class Solution(BaseModel):
    """A step-by-step solution to a math problem."""

    steps: list[Step]


class Scene(BaseModel):
    """One scene of a math video, with narration and visual content."""

    number: int
    title: str
    narration: str
    visual_type: Literal["graph", "equation", "geometry", "diagram", "table", "text"]
    animation_steps: list[str]
    # 1-based indices into the solution's steps. Scenes overlap by one step: a scene opens on
    # the step the previous one ended on, so it always has a starting picture to animate from.
    step_indices: list[int]


class ScenePlan(BaseModel):
    """A plan for a math video, with a list of scenes."""

    scenes: list[Scene]


class AnimationCode(BaseModel):
    """The Manim animation calls making up one scene's `construct()` body."""

    code: str


class SceneCode(BaseModel):
    """A complete Manim scene module."""

    code: str
