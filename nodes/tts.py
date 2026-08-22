"""tts_node — speak each scene's narration into an audio file.

`scene_planner_node` writes narration for the ear, spelling mathematics out
in words, so nothing here has to interpret notation.

Scene length is decided here, by how long the narration takes to say. That is
why `Scene` carries no duration of its own: before this point it could only
be guessed.
"""

from config.tts.base import BaseTTS
from graph.media import audio_dir, run_id, scene_stem
from graph.pipeline_state import PipelineState


def tts_node(state: PipelineState, tts: BaseTTS) -> PipelineState:
    """Synthesize narration audio for every scene.

    Args:
        state: Current pipeline state (reads `scenes` and `problem_statement`,
            which names the directory of this run).
        tts: Speech engine to narrate with.

    Returns:
        Updated pipeline state with `audio_files` and `scene_durations` set,
        one entry per scene.
    """
    run = run_id(state["problem_statement"])
    directory = audio_dir(run)

    audio_files: list[str] = []
    durations: list[float] = []
    for scene in state["scenes"]:
        destination = directory / f"{scene_stem(run, scene.number)}.wav"
        durations.append(tts.synthesize(scene.narration, destination))
        audio_files.append(str(destination))

    state["audio_files"] = audio_files
    state["scene_durations"] = durations

    return state
