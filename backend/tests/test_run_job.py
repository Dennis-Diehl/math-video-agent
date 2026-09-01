from pathlib import Path

import pytest

from graph.pipeline import build_pipeline
from graph.run_job import run
from nodes import assembler, executor
from tests.test_pipeline import FakeLLM, FakeTTS


@pytest.fixture
def no_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
        return Path(f"media/videos/{run}_scene_{scene_number}/l/Scene{scene_number}.mp4"), ""

    def fake_ffmpeg(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
        return destination, ""

    monkeypatch.setattr(executor, "_render", fake_render)
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg)


def test_run_yields_one_line_per_node_then_a_result_line(no_subprocesses: None):
    llm = FakeLLM(sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    lines = list(run(pipeline, "Solve x^2 - 4 = 0"))

    node_names = [line["node"] for line in lines]
    assert node_names == [
        "classifier",
        "solver",
        "scene_planner",
        "tts",
        "codegen",
        "executor",
        "assembler",
        None,
    ]
    assert lines[-1]["status"] == "done"
    assert lines[-1]["video"]


def test_run_reports_the_job_as_done_with_a_video(no_subprocesses: None):
    llm = FakeLLM(sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    *_, result = run(pipeline, "Solve x^2 - 4 = 0")

    assert result["node"] is None
    assert result["status"] == "done"
    assert result["video"]


def test_run_stops_early_and_reports_an_error_when_unsolvable(no_subprocesses: None):
    llm = FakeLLM(sympy_code="this is not python")
    pipeline = build_pipeline(llm=llm, cheap_llm=llm, tts=FakeTTS())

    lines = list(run(pipeline, "Draw me a house"))

    assert [line["node"] for line in lines] == ["classifier", "solver", None]
    assert lines[-1]["status"] == "error"
    assert lines[-1]["video"] is None
    assert "sympy could not evaluate" in (lines[-1]["detail"] or "")
