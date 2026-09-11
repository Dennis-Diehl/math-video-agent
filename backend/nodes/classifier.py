"""classifier_node — read a math problem's topic, difficulty and wording."""

from config.llm.base import BaseLLM, LLMUnavailableError
from config.schemas import Classification
from graph.pipeline_state import PipelineState
from nodes.solver import REPHRASE_HINT

CLASSIFIER_SYSTEM_PROMPT = """You are a math assistant reading a problem a student typed in.

### Rules
- Determine the problem's `topic` and its `difficulty` (the audience it is aimed at).
- Restate the problem as `problem_statement`: one clear, correct English sentence saying what \
is to be worked out. This wording is read out and shown as the introduction of an explanation \
video, so it has to stand on its own.
- Fix spelling, grammar and wording, translate anything that is not English, and drop filler \
such as greetings or "please".
- Never solve the problem, never add a hint, and never change what is being asked.
- Keep the mathematics exactly as given: the same numbers, the same expression, the same \
unknowns.
- Keep the mathematics in notation, e.g. "Solve the equation x^2 - 4 = 0 for x". Do not spell \
it out in words — later stages rewrite it for narration, and they need the precise notation \
to work from.

### Output Format
The problem's `topic`, its `difficulty`, and the restated `problem_statement`."""


def classifier_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Classify a math problem and clean up how it is worded."""
    prompt = f"Classify this math problem: '{state['user_input']}'"
    try:
        classification: Classification = llm.generate_structured(
            prompt, schema=Classification, system_prompt=CLASSIFIER_SYSTEM_PROMPT
        )
    except LLMUnavailableError as e:
        # Rephrasing the problem would not help here — the service itself
        # refused or could not be reached, not the wording.
        state["error"] = f"Could not reach the AI service: {e}"
        return state
    except Exception as e:  # noqa: BLE001 — the LLM call can raise any exception type
        state["error"] = f"Could not understand this as a math problem: {e}" + REPHRASE_HINT
        return state

    state["topic"] = classification.topic
    state["difficulty"] = classification.difficulty
    state["problem_statement"] = classification.problem_statement
    state["error"] = None

    return state
