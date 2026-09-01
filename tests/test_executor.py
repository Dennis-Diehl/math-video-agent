from pathlib import Path

import pytest

from config.llm.base import BaseLLM, T
from config.schemas import Scene, SceneCode, Step
from graph.media import run_id, scene_stem
from graph.pipeline_state import PipelineState
from nodes import executor
from nodes.executor import MAX_RENDER_ATTEMPTS, executor_node


class FakeLLM(BaseLLM):
    """A `BaseLLM` that returns canned corrected code and records its prompts."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["# corrected"]
        self.prompts: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        self.prompts.append(prompt)
        code = self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]
        return schema.model_validate(SceneCode(code=code).model_dump())


def make_state(problem: str, codes: list[str]) -> PipelineState:
    # One scene per code: `executor_node` reads both when a render fails and it
    # has to fall back to a title-only scene.
    scenes = [
        Scene(
            number=number,
            title="Factoring",
            narration="We factor the equation.",
            visual_type="equation",
            animation_steps=["Show the equation"],
            step_indices=[1],
        )
        for number in range(1, len(codes) + 1)
    ]
    return {
        "user_input": problem,
        "problem_statement": problem,
        "topic": "algebra",
        "difficulty": "school",
        "solution": [Step(explanation="Start.", expression="Eq(x**2 - 4, 0)")],
        "solvable": True,
        "scenes": scenes,
        "manim_codes": codes,
        "scene_videos": [],
        "audio_files": [],
        "scene_durations": [4.0] * len(codes),
        "final_video": "",
        "error": None,
    }


def test_run_id_is_stable_for_the_same_problem():
    assert run_id("Solve x**2 - 4 = 0") == run_id("Solve x**2 - 4 = 0")


def test_run_id_differs_between_problems():
    # Two problems rendered one after another must not share a directory,
    # or the second run silently overwrites the first one's videos.
    assert run_id("Solve x**2 - 4 = 0") != run_id("Differentiate x**3 + 2*x")


def test_scene_stem_keeps_runs_apart():
    equation = scene_stem(run_id("Solve x**2 - 4 = 0"), 1)
    derivative = scene_stem(run_id("Differentiate x**3 + 2*x"), 1)

    assert equation != derivative
    assert equation.endswith("_scene_1")


def test_executor_collects_one_video_per_scene(monkeypatch: pytest.MonkeyPatch):
    rendered: list[tuple[str, int]] = []

    def fake_render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        rendered.append((run, scene_number))
        return Path(f"media/videos/{run}_scene_{scene_number}/l/Scene{scene_number}.mp4"), ""

    monkeypatch.setattr(executor, "_render", fake_render)
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# one", "# two"]), FakeLLM())

    assert len(state["scene_videos"]) == 2
    assert state["error"] is None
    assert [number for _, number in rendered] == [1, 2]


def test_executor_writes_each_run_to_its_own_directory(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    def fake_render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        seen.append(run)
        return Path(f"media/videos/{run}_scene_{scene_number}/l/Scene{scene_number}.mp4"), ""

    monkeypatch.setattr(executor, "_render", fake_render)
    llm = FakeLLM()
    first = executor_node(make_state("Solve x**2 - 4 = 0", ["# a"]), llm)
    second = executor_node(make_state("Differentiate x**3 + 2*x", ["# a"]), llm)

    assert len(set(seen)) == 2
    assert first["scene_videos"] != second["scene_videos"]


def test_executor_corrects_code_between_failed_attempts(monkeypatch: pytest.MonkeyPatch):
    attempts: list[str] = []

    def fake_render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        attempts.append(code)
        if len(attempts) < 2:
            return None, "AttributeError: no attribute 'foo'"
        return Path("media/videos/x_scene_1/l/Scene1.mp4"), ""

    monkeypatch.setattr(executor, "_render", fake_render)
    llm = FakeLLM(["# corrected"])
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# broken"]), llm)

    assert attempts == ["# broken", "# corrected"]
    assert "AttributeError" in llm.prompts[0]
    assert state["error"] is None
    assert len(state["scene_videos"]) == 1


def test_executor_reports_a_scene_it_could_not_render(monkeypatch: pytest.MonkeyPatch):
    def fail_generated_code(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        if "Write(title)" in code:  # the title-only fallback scene
            return Path("media/videos/x_scene_1/l/Scene1.mp4"), ""
        return None, "LaTeX error"

    monkeypatch.setattr(executor, "_render", fail_generated_code)
    llm = FakeLLM()
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# broken"]), llm)

    assert state["error"] is not None
    assert "Scene 1" in state["error"]
    assert "LaTeX error" in state["error"]
    # The last attempt is not followed by a pointless correction call.
    assert len(llm.prompts) == MAX_RENDER_ATTEMPTS - 1


def test_executor_replaces_a_scene_it_could_not_render(monkeypatch: pytest.MonkeyPatch):
    rendered: list[str] = []

    def fail_generated_code(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        rendered.append(code)
        if "Write(title)" in code:
            return Path("media/videos/x_scene_1/l/Scene1.mp4"), ""
        return None, "LaTeX error"

    monkeypatch.setattr(executor, "_render", fail_generated_code)
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# broken"]), FakeLLM())

    # The scene keeps its slot, so audio and video stay paired by position.
    assert len(state["scene_videos"]) == 1
    assert state["scene_videos"][0] != ""
    assert "Write(title)" in rendered[-1]


def test_executor_leaves_a_gap_when_even_the_fallback_fails(monkeypatch: pytest.MonkeyPatch):
    def always_fails(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        return None, "LaTeX error"

    monkeypatch.setattr(executor, "_render", always_fails)
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# broken"]), FakeLLM())

    assert state["scene_videos"] == [""]
    assert "Scene 1 fallback" in (state["error"] or "")


def test_executor_keeps_rendered_scenes_when_one_fails(monkeypatch: pytest.MonkeyPatch):
    def fail_second(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        if scene_number == 2 and "Write(title)" not in code:
            return None, "LaTeX error"
        return Path(f"media/videos/x_scene_{scene_number}/l/Scene{scene_number}.mp4"), ""

    monkeypatch.setattr(executor, "_render", fail_second)
    state = executor_node(make_state("Solve x**2 - 4 = 0", ["# a", "# b", "# c"]), FakeLLM())

    assert len(state["scene_videos"]) == 3
    assert all(state["scene_videos"])
    assert "Scene 2" in (state["error"] or "")
