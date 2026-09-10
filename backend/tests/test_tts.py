from pathlib import Path

from config.schemas import Scene, Step
from config.tts.base import BaseTTS
from graph.media import run_id
from graph.pipeline_state import PipelineState
from nodes.tts import tts_node


class FakeTTS(BaseTTS):
    """A `BaseTTS` that records what it was asked to say instead of speaking."""

    def __init__(self, seconds: float = 3.0, raises: Exception | None = None) -> None:
        self.seconds = seconds
        self.raises = raises
        self.spoken: list[tuple[str, Path]] = []

    def synthesize(self, text: str, destination: Path) -> float:
        if self.raises is not None:
            raise self.raises
        self.spoken.append((text, destination))
        return self.seconds


def make_scene(number: int, narration: str) -> Scene:
    return Scene(
        number=number,
        title="Factoring",
        narration=narration,
        visual_type="equation",
        animation_steps=["Show the equation"],
        step_indices=[number, number + 1],
    )


def make_state(problem: str, scenes: list[Scene]) -> PipelineState:
    return {
        "user_input": problem,
        "problem_statement": problem,
        "topic": "algebra",
        "difficulty": "school",
        "solution": [Step(explanation="Start.", expression="Eq(x**2 - 4, 0)")],
        "solvable": True,
        "scenes": scenes,
        "manim_codes": [],
        "scene_videos": [],
        "audio_files": [],
        "scene_durations": [],
        "final_video": "",
        "error": None,
    }


def test_tts_writes_one_audio_file_per_scene():
    tts = FakeTTS()
    scenes = [make_scene(1, "First scene."), make_scene(2, "Second scene.")]

    state = tts_node(make_state("Solve x**2 - 4 = 0", scenes), tts)

    assert len(state["audio_files"]) == 2
    assert len(tts.spoken) == 2


def test_tts_speaks_the_narration_of_each_scene():
    tts = FakeTTS()
    scenes = [make_scene(1, "We add four to both sides."), make_scene(2, "That leaves x squared.")]

    tts_node(make_state("Solve x**2 - 4 = 0", scenes), tts)

    assert [text for text, _ in tts.spoken] == [
        "We add four to both sides.",
        "That leaves x squared.",
    ]


def test_tts_names_files_after_their_scene():
    tts = FakeTTS()
    scenes = [make_scene(1, "First."), make_scene(2, "Second.")]

    state = tts_node(make_state("Solve x**2 - 4 = 0", scenes), tts)

    assert state["audio_files"][0].endswith("_scene_1.wav")
    assert state["audio_files"][1].endswith("_scene_2.wav")


def test_tts_writes_each_run_to_its_own_directory():
    # Narrating a second problem must not overwrite the first one's audio.
    equation = tts_node(make_state("Solve x**2 - 4 = 0", [make_scene(1, "First.")]), FakeTTS())
    derivative = tts_node(make_state("Differentiate x**3", [make_scene(1, "First.")]), FakeTTS())

    assert equation["audio_files"] != derivative["audio_files"]


def test_tts_puts_audio_under_the_runs_directory():
    tts = FakeTTS()
    problem = "Solve x**2 - 4 = 0"

    state = tts_node(make_state(problem, [make_scene(1, "First.")]), tts)

    assert run_id(problem) in state["audio_files"][0]
    assert "audio" in state["audio_files"][0]


def test_tts_handles_a_solution_with_no_scenes():
    tts = FakeTTS()

    state = tts_node(make_state("Solve x**2 - 4 = 0", []), tts)

    assert state["audio_files"] == []
    assert tts.spoken == []


def test_tts_reports_the_error_when_synthesis_fails():
    tts = FakeTTS(raises=RuntimeError("model failed to load"))
    scenes = [make_scene(1, "First scene.")]

    state = tts_node(make_state("Solve x**2 - 4 = 0", scenes), tts)

    assert state["audio_files"] == []
    assert state["error"] is not None
    assert "Could not generate narration for this explanation" in state["error"]


def test_tts_error_does_not_suggest_rephrasing():
    tts = FakeTTS(raises=RuntimeError("model failed to load"))
    scenes = [make_scene(1, "First scene.")]

    state = tts_node(make_state("Solve x**2 - 4 = 0", scenes), tts)

    assert state["error"] is not None
    assert "more explicitly" not in state["error"]


def test_tts_clears_an_error_from_an_earlier_run():
    tts = FakeTTS()
    state = make_state("Solve x**2 - 4 = 0", [make_scene(1, "First.")])
    state["error"] = "left over from a previous run"

    assert tts_node(state, tts)["error"] is None
