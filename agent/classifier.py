"""classifier_node — detect a math problem's topic and difficulty."""

from llm.base import BaseLLM
from schemas import Classification
from state.pipeline_state import PipelineState


def classifier_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Classify the topic and difficulty of a math problem.

    Args:
        state: Current pipeline state (reads `user_input`).
        llm: LLM client to use for classification.

    Returns:
        Updated pipeline state with `topic` and `difficulty` set.
    """
    prompt = f"Classify this math problem: '{state['user_input']}'"
    classification: Classification = llm.generate_structured(prompt, schema=Classification)
    state['topic'] = classification.topic
    state['difficulty'] = classification.difficulty

    return state