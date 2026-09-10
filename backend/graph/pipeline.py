"""Assembles the LangGraph pipeline and decides which model each node gets.
Nodes are bound to their `llm`/`tts` via `functools.partial`, since LangGraph
only passes state.
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


def _classified(state: PipelineState) -> str:
    """Stop the run when the problem could not be classified."""
    return END if state["error"] else "solver"


def _solved(state: PipelineState) -> str:
    """Stop the run when the problem could not be solved."""
    return END if state["error"] else "scene_planner"


def _planned(state: PipelineState) -> str:
    """Stop the run when the scenes could not be planned."""
    return END if state["error"] else "tts"


def _narrated(state: PipelineState) -> str:
    """Stop the run when narration could not be generated."""
    return END if state["error"] else "codegen"


def _coded(state: PipelineState) -> str:
    """Stop the run when the scene animation code could not be generated."""
    return END if state["error"] else "executor"


def _rendered(state: PipelineState) -> str:
    """Skip assembly when not a single scene produced a video."""
    return "assembler" if any(state["scene_videos"]) else END


def build_pipeline(llm: BaseLLM, cheap_llm: BaseLLM, tts: BaseTTS) -> CompiledStateGraph:
    """Assemble the pipeline. `cheap_llm` handles classification, `llm` everything else."""
    graph = StateGraph(PipelineState)

    graph.add_node("classifier", partial(classifier_node, llm=cheap_llm))
    graph.add_node("solver", partial(solver_node, llm=llm))
    graph.add_node("scene_planner", partial(scene_planner_node, llm=llm))
    graph.add_node("tts", partial(tts_node, tts=tts))
    graph.add_node("codegen", partial(codegen_node, llm=llm))
    graph.add_node("executor", partial(executor_node, llm=llm))
    graph.add_node("assembler", assembler_node)

    graph.add_edge(START, "classifier")
    graph.add_conditional_edges("classifier", _classified, {"solver": "solver", END: END})
    graph.add_conditional_edges("solver", _solved, {"scene_planner": "scene_planner", END: END})
    graph.add_conditional_edges("scene_planner", _planned, {"tts": "tts", END: END})
    graph.add_conditional_edges("tts", _narrated, {"codegen": "codegen", END: END})
    graph.add_conditional_edges("codegen", _coded, {"executor": "executor", END: END})
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
    """Turn a math problem into a video, using the configured Gemini and Kokoro clients."""
    pipeline = build_pipeline(
        llm=GeminiLLM(settings.gemini_model_flash, settings.gemini_api_key),
        cheap_llm=GeminiLLM(settings.gemini_model_flash_lite, settings.gemini_api_key),
        tts=KokoroTTS(settings.kokoro_voice, settings.kokoro_lang_code),
    )
    return cast(PipelineState, pipeline.invoke(initial_state(user_input)))
