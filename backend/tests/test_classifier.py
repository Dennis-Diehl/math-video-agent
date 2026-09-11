from config.llm.base import BaseLLM, LLMUnavailableError, T
from config.schemas import Classification
from graph.pipeline_state import PipelineState
from nodes.classifier import classifier_node


class FakeLLM(BaseLLM):
    """A `BaseLLM` returning a canned classification, or raising if told to."""

    def __init__(
        self, classification: Classification | None = None, raises: Exception | None = None
    ):
        self.classification = classification or Classification(
            topic="algebra", difficulty="school", problem_statement="Solve x**2 - 4 = 0"
        )
        self.raises = raises

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        if self.raises is not None:
            raise self.raises
        return schema.model_validate(self.classification.model_dump())


def make_state(problem: str) -> PipelineState:
    return {
        "user_input": problem,
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


def test_classifier_classifies_a_math_problem():
    llm = FakeLLM()

    state = classifier_node(make_state("solve x^2 - 4 = 0"), llm)

    assert state["error"] is None
    assert state["topic"] == "algebra"
    assert state["difficulty"] == "school"
    assert state["problem_statement"] == "Solve x**2 - 4 = 0"


def test_classifier_reports_the_error_when_the_llm_call_fails():
    llm = FakeLLM(raises=ValueError("Gemini returned no text"))

    state = classifier_node(make_state("asdlkjasd"), llm)

    assert state["topic"] == ""
    assert state["difficulty"] == ""
    assert state["problem_statement"] == ""
    assert state["error"] is not None
    assert "Could not understand this as a math problem" in state["error"]


def test_classifier_error_tells_the_user_how_to_rephrase():
    llm = FakeLLM(raises=ValueError("Gemini returned no text"))

    state = classifier_node(make_state("asdlkjasd"), llm)

    assert state["error"] is not None
    assert "more explicitly" in state["error"]


def test_classifier_reports_an_api_error_without_the_rephrase_hint():
    llm = FakeLLM(raises=LLMUnavailableError("429 RESOURCE_EXHAUSTED"))

    state = classifier_node(make_state("solve x^2 - 4 = 0"), llm)

    assert state["error"] is not None
    assert "Could not reach the AI service" in state["error"]
    assert "more explicitly" not in state["error"]


def test_classifier_clears_an_error_from_an_earlier_run():
    llm = FakeLLM()
    state = make_state("solve x^2 - 4 = 0")
    state["error"] = "left over from a previous run"

    assert classifier_node(state, llm)["error"] is None
