"""tts_node — speak each scene's narration into an audio file, setting each
scene's duration.
"""

from config.tts.base import BaseTTS
from graph.media import audio_dir, run_id, scene_stem
from graph.pipeline_state import PipelineState


def tts_node(state: PipelineState, tts: BaseTTS) -> PipelineState:
    """Synthesize narration audio for every scene."""
    run = run_id(state["problem_statement"])
    directory = audio_dir(run)

    audio_files: list[str] = []
    durations: list[float] = []
    for scene in state["scenes"]:
        destination = directory / f"{scene_stem(run, scene.number)}.wav"
        try:
            durations.append(tts.synthesize(scene.narration, destination))
        except Exception as e:  # noqa: BLE001 — the TTS call can raise any exception type
            state["error"] = f"Could not generate narration for this explanation: {e}"
            return state
        audio_files.append(str(destination))

    state["audio_files"] = audio_files
    state["scene_durations"] = durations
    state["error"] = None

    return state
