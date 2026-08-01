"""Pydantic schemas shared across pipeline nodes.

These are the structured-output contracts that `BaseLLM.generate_structured`
validates LLM responses against.
"""

from typing import Literal

from pydantic import BaseModel


class Classification(BaseModel):
    """Topic and difficulty of a math problem."""

    topic: Literal[
        "algebra", "geometry", "trigonometry", "calculus", "linear_algebra", "probability"
    ]
    difficulty: Literal["school", "university"]
