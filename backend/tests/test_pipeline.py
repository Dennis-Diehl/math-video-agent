from pathlib import Path

import pytest
from pydantic import BaseModel

from config.llm.base import BaseLLM, T
from config.schemas import (
    AnimationCode,
    Classification,
    Extraction,
    Scene,
    SceneCode,
    ScenePlan,
    Solution,
    Step,
)
from config.tts.base import BaseTTS
from graph.pipeline import build_pipeline, initial_state
from nodes import assembler, executor


class FakeLLM(BaseLLM):
    """A `BaseLLM` answering every schema the pipeline asks for.

    The pipeline calls one client for four different nodes, so the schema
    decides the answer. `sympy_code` is the one thing a test varies, since it
    is what makes a problem solvable or not.
    """

    def __init__(self, sympy_code: str = "result = sp.Integer(2)"):
        self.sympy_code = sympy_code
        self.schemas: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        self.schemas.append(schema.__name__)
        answers: dict[str, BaseModel] = {
            "Classification": Classification(
                topic="algebra", difficulty="school", problem_statement="Solve x**2 - 4 = 0"
            ),
            "Extraction": Extraction(sympy_code=self.sympy_code),
            "Solution": Solution(
                steps=[
                    Step(explanation="Start.", expression="Eq(x**2 - 4, 0)"),
                    Step(explanation="Add four.", expression="Eq(x**2, 4)"),
                ]
            ),
            "ScenePlan": ScenePlan(
                scenes=[
                    Scene(
                        number=1,
                        title="Solving",
                        narration="We add four to both sides.",
                        visual_type="equation",
                        animation_steps=["Show the equation"],
                        step_indices=[1, 2],
                    )
                ]
            ),
            "AnimationCode": AnimationCode(code="self.play(Write(formula_1))\nself.wait(1)"),
            "SceneCode": SceneCode(code="# corrected"),
        }
        return schema.model_validate(answers[schema.__name__].model_dump())


class FakeTTS(BaseTTS):
    """A `BaseTTS` that reports a duration without synthesizing anything."""

    def synthesize(self, text: str, destination: Path) -> float:
        return 4.0


@pytest.fixture
def no_subprocesses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the Manim and ffmpeg boundaries, recording which ones ran."""
    ran: list[str] = []

    def fake_render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        ran.append("manim")
        return Path(f"media/videos/{run}_scene_{scene_number}/l/Scene{scene_number}.mp4"), ""

    def fake_ffmpeg(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
        ran.append("ffmpeg")
        return destination, ""

    monkeypatch.setattr(executor, "_render", fake_render)
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg)
    return ran


def test_pipeline_turns_a_problem_into_a_video(no_subprocesses: list[str]):
    llm = FakeLLM(sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    state = pipeline.invoke(initial_state("Solve x^2 - 4 = 0"))

    assert state["error"] is None
    assert state["final_video"].endswith(".mp4")
    assert no_subprocesses == ["manim", "ffmpeg", "ffmpeg"]


def test_pipeline_runs_every_node_in_order(no_subprocesses: list[str]):
    llm = FakeLLM(sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    pipeline.invoke(initial_state("Solve x^2 - 4 = 0"))

    assert llm.schemas[:4] == ["Classification", "Extraction", "Solution", "ScenePlan"]


def test_pipeline_stops_when_the_problem_cannot_be_solved(no_subprocesses: list[str]):
    llm = FakeLLM(sympy_code="this is not python")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    state = pipeline.invoke(initial_state("Draw me a house"))

    assert state["final_video"] == ""
    assert "sympy could not evaluate" in state["error"]
    # Nothing was rendered or assembled, and no scenes were planned.
    assert no_subprocesses == []
    assert "ScenePlan" not in llm.schemas


def test_pipeline_skips_assembly_when_no_scene_rendered(monkeypatch: pytest.MonkeyPatch):
    def always_fails(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        return None, "LaTeX error"

    def unexpected_ffmpeg(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
        raise AssertionError("assembler ran without a single video")

    monkeypatch.setattr(executor, "_render", always_fails)
    monkeypatch.setattr(assembler, "_run_ffmpeg", unexpected_ffmpeg)
    llm = FakeLLM(sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    state = pipeline.invoke(initial_state("Solve x^2 - 4 = 0"))

    assert state["final_video"] == ""
    assert "LaTeX error" in state["error"]
