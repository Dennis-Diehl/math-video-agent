"""Sandbox entrypoint: run one pipeline call, print progress as JSON lines.

`api/jobs.py` starts this across a container boundary and can only see
stdout, hence JSON lines instead of a return value.
"""

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from config.config import settings
from config.llm.gemini import GeminiLLM
from config.tts.kokoro import KokoroTTS
from graph.pipeline import build_pipeline, initial_state
from graph.pipeline_state import PipelineState
from graph.progress import ProgressLine

OUTPUT_DIR = Path("/output")


def run(pipeline: CompiledStateGraph, problem: str) -> Iterator[ProgressLine]:
    """Run a compiled pipeline, yielding one line per finished node.

    Last line has `node=None`: the job's own outcome. A node's `detail` can
    be set without ending the run, so no per-node line is itself the result.
    """
    state: PipelineState | None = None
    for update in pipeline.stream(initial_state(problem)):
        ((node_name, state),) = update.items()
        yield {
            "node": node_name,
            "status": "done",
            "detail": state.get("error"),
            "video": None,
        }

    assert state is not None  # classifier always runs first
    video = state.get("final_video") or None
    yield {
        "node": None,
        "status": "done" if video else "error",
        "detail": state.get("error"),
        "video": video,
    }


def main() -> None:
    """Read the job from the environment, run it, print progress, save the video."""
    problem = os.environ["PROBLEM"]
    pipeline = build_pipeline(
        llm=GeminiLLM(settings.gemini_model_flash, settings.gemini_api_key),
        cheap_llm=GeminiLLM(settings.gemini_model_flash_lite, settings.gemini_api_key),
        tts=KokoroTTS(settings.kokoro_voice, settings.kokoro_lang_code),
    )

    for line in run(pipeline, problem):
        print(json.dumps(line), flush=True)  # flush: the parent reads this live, not at exit
        if line["video"]:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy(line["video"], OUTPUT_DIR / "final.mp4")


if __name__ == "__main__":
    main()
