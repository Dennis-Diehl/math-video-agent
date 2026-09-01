from pathlib import Path

import pytest

from config.schemas import Step
from graph.media import run_id
from graph.pipeline_state import PipelineState
from nodes import assembler
from nodes.assembler import assembler_node


def make_state(problem: str, videos: list[str], audios: list[str]) -> PipelineState:
    return {
        "user_input": problem,
        "problem_statement": problem,
        "topic": "algebra",
        "difficulty": "school",
        "solution": [Step(explanation="Start.", expression="Eq(x**2 - 4, 0)")],
        "solvable": True,
        "scenes": [],
        "manim_codes": [],
        "scene_videos": videos,
        "audio_files": audios,
        "scene_durations": [4.0] * len(videos),
        "final_video": "",
        "error": None,
    }


def fake_ffmpeg(calls: list[list[str]], fails_on: str = ""):
    """Replace the ffmpeg boundary, recording arguments instead of running it."""

    def run(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
        calls.append(arguments)
        if fails_on and fails_on in " ".join(arguments):
            return None, "Invalid data found when processing input"
        return destination, ""

    return run


def two_scenes() -> PipelineState:
    return make_state(
        "Solve x**2 - 4 = 0",
        ["media/videos/a/Scene1.mp4", "media/videos/b/Scene2.mp4"],
        ["media/audio/a/scene_1.wav", "media/audio/b/scene_2.wav"],
    )


def test_assembler_muxes_every_scene_then_joins_them(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))

    state = assembler_node(two_scenes())

    # One mux per scene, plus one concat.
    assert len(calls) == 3
    assert state["error"] is None
    assert state["final_video"].endswith(f"{run_id('Solve x**2 - 4 = 0')}.mp4")


def test_assembler_pads_the_audio_rather_than_cutting_the_picture(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))

    assembler_node(two_scenes())

    assert "apad" in calls[0]
    assert "-shortest" in calls[0]


def test_assembler_puts_the_index_at_the_front_of_the_finished_video(
    monkeypatch: pytest.MonkeyPatch,
):
    # Without this the audio track is invisible to a player that starts
    # decoding before it has read the end of the file.
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))

    assembler_node(two_scenes())

    concat = calls[-1]
    assert concat[concat.index("-movflags") + 1] == "+faststart"


def test_assembler_copies_the_picture_instead_of_re_encoding(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))

    assembler_node(two_scenes())

    assert calls[0][calls[0].index("-c:v") + 1] == "copy"


def test_assembler_skips_a_scene_the_executor_could_not_render(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))
    state = two_scenes()
    state["scene_videos"] = ["media/videos/a/Scene1.mp4", ""]

    result = assembler_node(state)

    # The empty scene takes its narration with it: one mux, then the concat.
    assert len(calls) == 2
    assert result["final_video"] != ""


def test_assembler_reports_a_scene_it_could_not_join(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls, fails_on="Scene2"))

    state = assembler_node(two_scenes())

    assert state["error"] is not None
    assert "Scene 2" in state["error"]
    # The scene that worked still makes it into the video.
    assert state["final_video"] != ""


def test_assembler_reports_a_failed_join(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls, fails_on="concat"))

    state = assembler_node(two_scenes())

    assert state["final_video"] == ""
    assert "Joining the scenes failed" in (state["error"] or "")


def test_assembler_reports_having_nothing_to_assemble(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))

    state = assembler_node(make_state("Solve x**2 - 4 = 0", [], []))

    assert calls == []
    assert state["final_video"] == ""
    assert "no video" in (state["error"] or "")


def test_assembler_keeps_an_error_reported_by_an_earlier_node(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(assembler, "_run_ffmpeg", fake_ffmpeg(calls))
    state = two_scenes()
    state["error"] = "Scene 2: LaTeX error"

    result = assembler_node(state)

    assert result["final_video"] != ""
    assert "LaTeX error" in (result["error"] or "")
