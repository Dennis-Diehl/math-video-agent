"""The assembled LangGraph pipeline.

Wires the nodes into one graph and decides which model each of them gets.
Nodes take an `llm` or a `tts` alongside the state, which LangGraph does not
pass, so each one is bound to its client with `functools.partial` before being
added to the graph.

The path forks in two places, both where a node has already done what recovery
it could: `solver_node` stops the run when sympy cannot solve the problem at
all, and a set of scenes with no usable video skips assembly.
"""

from functools import partial
from typing import cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config.config import settings
from config.llm.base import BaseLLM
from config.llm.gemini import GeminiLLM
from config.tts.base import BaseTTS
from config.tts.kokoro import KokoroTTS
from graph.pipeline_state import PipelineState
from nodes.assembler import assembler_node
from nodes.classifier import classifier_node
from nodes.codegen import codegen_node
from nodes.executor import executor_node
from nodes.scene_planner import scene_planner_node
from nodes.solver import solver_node
from nodes.tts import tts_node


def _solved(state: PipelineState) -> str:
    """Stop the run when the problem could not be solved.

    `solver_node` has already exhausted its retries at this point, and its
    `error` explains to the user what to reword. Everything downstream needs
    `solution`, so there is nothing left to do.
    """
    return END if state["error"] else "scene_planner"


def _rendered(state: PipelineState) -> str:
    """Skip assembly when not a single scene produced a video.

    An empty entry in `scene_videos` means even the executor's replacement
    scene would not render. If that happened to every scene there is nothing
    to join.
    """
    return "assembler" if any(state["scene_videos"]) else END


def build_pipeline(llm: BaseLLM, cheap_llm: BaseLLM, tts: BaseTTS) -> CompiledStateGraph:
    """Assemble the pipeline.

    Args:
        llm: Client for the nodes that reason about mathematics — solving,
            planning scenes, writing and correcting Manim code.
        cheap_llm: Client for classification, which picks from a fixed set of
            answers and does not need the stronger model.
        tts: Engine that speaks each scene's narration.

    Returns:
        The compiled graph, ready to `invoke` with an initial state.
    """
    graph = StateGraph(PipelineState)

    graph.add_node("classifier", partial(classifier_node, llm=cheap_llm))
    graph.add_node("solver", partial(solver_node, llm=llm))
    graph.add_node("scene_planner", partial(scene_planner_node, llm=llm))
    graph.add_node("tts", partial(tts_node, tts=tts))
    graph.add_node("codegen", partial(codegen_node, llm=llm))
    graph.add_node("executor", partial(executor_node, llm=llm))
    graph.add_node("assembler", assembler_node)

    graph.add_edge(START, "classifier")
    graph.add_edge("classifier", "solver")
    graph.add_conditional_edges("solver", _solved, {"scene_planner": "scene_planner", END: END})
    # Narration comes before code generation: it decides how long a scene is,
    # which is what `codegen_node` times the animations against.
    graph.add_edge("scene_planner", "tts")
    graph.add_edge("tts", "codegen")
    graph.add_edge("codegen", "executor")
    graph.add_conditional_edges("executor", _rendered, {"assembler": "assembler", END: END})
    graph.add_edge("assembler", END)

    return graph.compile()


def initial_state(user_input: str) -> PipelineState:
    """Build the state a run starts from, with every field at its empty value."""
    return {
        "user_input": user_input,
        "problem_statement": "",
        "topic": "",
        "difficulty": "",
        "solution": [],
        "solvable": False,
        "scenes": [],
        "manim_codes": [],
        "scene_videos": [],
        "audio_files": [],
        "scene_durations": [],
        "final_video": "",
        "error": None,
    }


def run_pipeline(user_input: str) -> PipelineState:
    """Turn a math problem into a video, using the configured Gemini and Kokoro clients.

    Args:
        user_input: The problem as the user wrote it.

    Returns:
        The final state. `final_video` holds the finished file when there is
        one; `error` explains what went wrong or which scenes had to be
        replaced. Both can be set at once — a video with a replaced scene is
        still a video.
    """
    pipeline = build_pipeline(
        llm=GeminiLLM(settings.gemini_model_flash, settings.gemini_api_key),
        cheap_llm=GeminiLLM(settings.gemini_model_flash_lite, settings.gemini_api_key),
        tts=KokoroTTS(settings.kokoro_voice, settings.kokoro_lang_code),
    )

    # `invoke` is typed as returning a plain dict; the graph was built from
    # `PipelineState`, so the keys are the ones declared there.
    return cast(PipelineState, pipeline.invoke(initial_state(user_input)))
