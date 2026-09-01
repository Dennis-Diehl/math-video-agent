"""executor_node — render each scene's Manim code into a video file.

Rendering is where mistakes in generated code actually surface: `codegen_node`
only compiles the code, which catches syntax errors but not Manim runtime
errors (an animation that does not fit its object, LaTeX that fails to
typeset). Each scene therefore gets several attempts, and after a failed
render the error output is handed back to the LLM to correct the code before
trying again.
"""

import shutil
import subprocess
from pathlib import Path

from config.llm.base import BaseLLM
from config.schemas import SceneCode
from graph.media import MEDIA_DIR, RENDER_QUALITY, run_id, scene_dir, scene_stem
from graph.pipeline_state import PipelineState
from nodes.codegen import fallback_code

MAX_RENDER_ATTEMPTS = 3
RENDER_TIMEOUT_SECONDS = 300

# How much of Manim's output to keep when reporting a failure. Tracebacks are
# long and the useful part is at the end.
ERROR_TAIL_CHARS = 2000

CORRECTION_SYSTEM_PROMPT = """You are a Manim expert fixing a scene that failed to render.

### Rules
- Return the complete corrected module, not a diff and not an explanation.
- Change as little as possible: fix only what the error message points at.
- Never change the mathematical content. Every `MathTex` string must keep the \
exact LaTeX it already has, because those formulas are already verified.
- Keep the class name, the `construct()` method and the subtitle exactly as they are.
- Typical causes: an animation that does not suit its object (use `Create` for axes, \
graphs and tables, `Write` for text and formulas), referencing an object that was \
never defined, or animating an object that is already on screen.
- Do not add imports beyond the ones already present.

### Output Format
The full corrected Python module, starting with its imports and containing exactly \
one Scene class."""


def _rendered_video(run: str, scene_number: int) -> Path | None:
    """Locate the video Manim produced for a scene.

    Manim writes to `<media_dir>/videos/<file stem>/<quality>/<SceneName>.mp4`.
    The quality folder depends on the render flags, so it is matched with a
    wildcard — but only one level deep, to skip the partial movie files Manim
    keeps in a subfolder.
    """
    stem = scene_stem(run, scene_number)
    pattern = f"videos/{stem}/*/Scene{scene_number}.mp4"
    return next(iter(sorted(MEDIA_DIR.glob(pattern))), None)


def _render(code: str, run: str, scene_number: int) -> tuple[Path | None, str]:
    """Write a scene's code to disk and render it.

    Returns the path to the rendered video, or `None` plus the error output if
    rendering failed.
    """
    directory = scene_dir(run)
    directory.mkdir(parents=True, exist_ok=True)
    stem = scene_stem(run, scene_number)
    scene_file = directory / f"{stem}.py"
    scene_file.write_text(code)

    # Drop output from an earlier attempt, so a stale video from a previous
    # render can never be mistaken for this attempt succeeding.
    shutil.rmtree(MEDIA_DIR / "videos" / stem, ignore_errors=True)

    # This runs LLM-generated code in a separate process. That is not a
    # sandbox — see the design doc's note on sandboxing before deployment.
    try:
        result = subprocess.run(
            [
                "manim",
                "render",
                "--quality",
                RENDER_QUALITY,
                "--media_dir",
                str(MEDIA_DIR),
                str(scene_file),
                f"Scene{scene_number}",
            ],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"Rendering timed out after {RENDER_TIMEOUT_SECONDS} seconds."
    except FileNotFoundError:
        return None, "The `manim` command was not found."

    if result.returncode != 0:
        return None, (result.stderr or result.stdout)[-ERROR_TAIL_CHARS:]

    video = _rendered_video(run, scene_number)
    if video is None:
        return None, "Manim reported success but produced no video file."

    return video, ""


def _correct(llm: BaseLLM, code: str, error: str) -> str:
    """Ask the LLM to fix code that failed to render."""
    corrected: SceneCode = llm.generate_structured(
        prompt=(
            f"This Manim scene failed to render:\n\n{code}\n\n"
            f"Manim reported:\n{error}\n\n"
            "Return the corrected module."
        ),
        schema=SceneCode,
        system_prompt=CORRECTION_SYSTEM_PROMPT,
    )
    return corrected.code


def _render_with_retries(
    llm: BaseLLM, code: str, run: str, scene_number: int
) -> tuple[Path | None, str]:
    """Render a scene, correcting the code between failed attempts."""
    error = ""

    for attempt in range(MAX_RENDER_ATTEMPTS):
        video, error = _render(code, run, scene_number)
        if video is not None:
            return video, ""
        if attempt < MAX_RENDER_ATTEMPTS - 1:
            code = _correct(llm, code, error)

    return None, error


def executor_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Render every scene, correcting code that fails to render.

    A scene that still fails after every attempt is replaced by a title-only
    scene rather than dropped, so its narration keeps a picture and the videos
    stay aligned with `audio_files` position by position.

    Args:
        state: Current pipeline state (reads `manim_codes`, `scenes`,
            `scene_durations`, and `problem_statement`, which names the
            directory of this run).
        llm: LLM client used to correct code between failed render attempts.

    Returns:
        Updated pipeline state with `scene_videos` holding one entry per scene
        — empty for a scene whose replacement would not render either — and
        `error` reporting the scenes that had to be replaced.
    """
    run = run_id(state["problem_statement"])
    videos: list[str] = []
    failures: list[str] = []

    for position, code in enumerate(state["manim_codes"], start=1):
        video, error = _render_with_retries(llm, code, run, position)

        if video is None:
            failures.append(f"Scene {position}: {error}")
            scene = state["scenes"][position - 1]
            seconds = state["scene_durations"][position - 1]
            video, error = _render(fallback_code(scene, seconds), run, position)
            if video is None:
                failures.append(f"Scene {position} fallback: {error}")

        videos.append(str(video) if video is not None else "")

    state["scene_videos"] = videos
    state["error"] = "\n".join(failures) if failures else None

    return state
