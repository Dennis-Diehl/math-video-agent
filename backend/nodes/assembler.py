"""assembler_node — join every scene's picture and narration into one video,
via two ffmpeg passes (mux, then concat), no re-encoding.
"""

import subprocess
from pathlib import Path

from graph.media import assembled_dir, final_video, run_id, scene_stem
from graph.pipeline_state import PipelineState

ASSEMBLY_TIMEOUT_SECONDS = 120
ERROR_TAIL_CHARS = 2000  # error is at the end of ffmpeg's output


def _run_ffmpeg(arguments: list[str], destination: Path) -> tuple[Path | None, str]:
    """Run one ffmpeg command. Returns the written file, or `None` plus the
    error output on failure."""
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
    """Give one scene's silent video its narration. `apad` + `-shortest` pads
    the audio to the picture's length — safe since the picture is never
    shorter than the narration.
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
    """Join the finished scenes into one video, in order, via ffmpeg's concat
    demuxer. `+faststart` moves the index to the front — without it, players
    that start decoding early see no audio track and play silently.
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
    """Join picture and narration into the finished video. No LLM: ffmpeg
    failures come from the media, not generated code, so nothing to correct.
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

    state["error"] = "\n".join(filter(None, [state["error"], *failures])) or None

    return state
