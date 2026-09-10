import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from graph import run_job
from graph.pipeline import build_pipeline
from graph.run_job import main, run
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


class _ExplodingPipeline:
    """Fake compiled pipeline whose `.stream()` yields a normal update, then
    raises — simulating a node hitting an uncaught exception (e.g. an LLM
    call failing outright, not a sympy/render failure the node already
    handles itself)."""

    def stream(self, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield {"classifier": {**state, "error": None}}
        raise RuntimeError("boom: the LLM call failed")


def test_main_reports_a_terminal_error_line_when_a_node_raises_uncaught(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A node raising mid-stream must still produce a terminal `node: None`
    line with a real error message, not a silent process crash."""
    monkeypatch.setenv("PROBLEM", "hallo")
    monkeypatch.setattr(run_job, "build_pipeline", lambda **kwargs: _ExplodingPipeline())
    monkeypatch.setattr(run_job, "GeminiLLM", lambda *args, **kwargs: object())
    monkeypatch.setattr(run_job, "KokoroTTS", lambda *args, **kwargs: object())

    main()

    lines = [json.loads(text) for text in capsys.readouterr().out.splitlines()]

    assert [line["node"] for line in lines] == ["classifier", None]
    result = lines[-1]
    assert result["status"] == "error"
    assert result["video"] is None
    assert result["detail"] is not None
    assert "boom: the LLM call failed" in result["detail"]
    # Not the generic infra-level fallback api/jobs.py falls back to when no
    # terminal line is ever seen.
    assert "stopped unexpectedly" not in result["detail"]
