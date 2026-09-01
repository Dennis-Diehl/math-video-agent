"""assembler_node — join every scene's picture and narration into one video.

Two ffmpeg passes: each scene's silent video is given its narration, then the
scenes are concatenated. Both run without re-encoding the picture, so the pass
costs seconds rather than minutes and loses no quality.

Timing is already settled by the time this runs. `codegen_node` stretched each
scene's pauses to cover its narration, so a scene's picture is never shorter
than its words — the only thing left to do here is pad the trailing silence.
"""

import subprocess
from pathlib import Path

from graph.media import assembled_dir, final_video, run_id, scene_stem
from graph.pipeline_state import PipelineState

# Joining copies the picture through untouched, so even a long video is quick.
ASSEMBLY_TIMEOUT_SECONDS = 120

# How much of ffmpeg's output to keep when reporting a failure. It reports the
# codecs it saw before the actual error, which comes last.
ERROR_TAIL_CHARS = 2000


def _run_ffmpeg(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
    """Run one ffmpeg command.

    Args:
        arguments: The command line after `ffmpeg -y`.
        destination: The file ffmpeg is expected to write.

    Returns:
        The written file, or `None` plus the error output if ffmpeg failed.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", *arguments],
            capture_output=True,
            text=True,
            timeout=ASSEMBLY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"ffmpeg timed out after {ASSEMBLY_TIMEOUT_SECONDS} seconds."
    except FileNotFoundError:
        return None, "The `ffmpeg` command was not found."

    if result.returncode != 0:
        return None, (result.stderr or result.stdout)[-ERROR_TAIL_CHARS:]

    if not destination.exists():
        return None, "ffmpeg reported success but produced no file."

    return destination, ""


def _mux(video: Path, audio: Path, destination: Path) -> tuple[Path | None, str]:
    """Give one scene's silent video its narration.

    `apad` extends the narration with silence and `-shortest` ends the result
    with the picture, which fills the gap left when a scene's animations run
    on past its words. This cannot cut the narration short: `_fit_timing` in
    `codegen_node` sizes every scene to at least its narration and rounds up to
    whole frames, so the picture always outlasts the audio.
    """
    return _run_ffmpeg(
        [
            "-i",
            str(video),
            "-i",
            str(audio),
            "-af",
            "apad",
            "-shortest",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(destination),
        ],
        destination,
    )


def _concat(scenes: list[Path], destination: Path) -> tuple[Path | None, str]:
    """Join the finished scenes into one video, in order.

    Uses ffmpeg's concat demuxer, which stitches streams together without
    re-encoding. It requires every input to share codecs and parameters — true
    here, since all scenes come from the same Manim render profile and the same
    audio encode in `_mux`.

    `+faststart` moves the index to the front of the file. Without it ffmpeg
    leaves the index at the end, and a player that starts decoding before it
    has read that far never learns the file has an audio track: the video plays
    silently in a browser or a notebook, while ffprobe reports sound because it
    reads the whole file first.

    The listing goes next to the scenes rather than next to the finished video,
    so it stays inside the run's own directory.
    """
    listing = scenes[0].parent / "concat.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("".join(f"file '{scene.resolve()}'\n" for scene in scenes))

    return _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        destination,
    )


def assembler_node(state: PipelineState) -> PipelineState:
    """Join picture and narration into the finished video.

    Takes no LLM: an ffmpeg failure comes from the media, not from generated
    code, so there is nothing for a model to correct. Failures are reported
    rather than retried.

    Args:
        state: Current pipeline state (reads `scene_videos`, `audio_files` and
            `problem_statement`, which names the directory of this run). A
            scene the executor could not render at all has an empty entry in
            `scene_videos` and is left out of the video entirely.

    Returns:
        Updated pipeline state with `final_video` set to the finished file, and
        `error` extended by whatever could not be assembled.
    """
    run = run_id(state["problem_statement"])
    directory = assembled_dir(run)
    assembled: list[Path] = []
    failures: list[str] = []

    for position, (video, audio) in enumerate(
        zip(state["scene_videos"], state["audio_files"]), start=1
    ):
        if not video:
            continue
        destination = directory / f"{scene_stem(run, position)}.mp4"
        scene, error = _mux(Path(video), Path(audio), destination)
        if scene is None:
            failures.append(f"Scene {position}: {error}")
            continue
        assembled.append(scene)

    if assembled:
        video_path, error = _concat(assembled, final_video(run))
        if video_path is None:
            failures.append(f"Joining the scenes failed: {error}")
        state["final_video"] = str(video_path) if video_path is not None else ""
    else:
        state["final_video"] = ""
        failures.append("No scene could be assembled, so there is no video.")

    # Keep what earlier nodes reported: a scene the executor had to replace is
    # still worth knowing about once the video exists.
    state["error"] = "\n".join(filter(None, [state["error"], *failures])) or None

    return state
