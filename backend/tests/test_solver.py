from config.llm.base import BaseLLM, LLMUnavailableError, T
from config.schemas import Extraction, Solution, Step
from graph.pipeline_state import PipelineState
from nodes.solver import MAX_EXPLANATION_ATTEMPTS, solver_node


class FakeLLM(BaseLLM):
    """A `BaseLLM` returning canned sympy code and solution steps.

    `solver_node` calls it twice with different schemas: once for `Extraction`,
    then repeatedly for `Solution`. The schema decides which canned answer to
    hand back, so a test only has to state the two it cares about. `fails_on`
    raises instead of answering, for the schema named, to simulate that call's
    LLM request failing outright — `fails_with` picks which exception, so a
    test can simulate either a generic LLM failure or the service itself
    being unreachable.
    """

    def __init__(
        self,
        sympy_code: str,
        steps: list[Step] | None = None,
        fails_on: str | None = None,
        fails_with: Exception | None = None,
    ):
        self.sympy_code = sympy_code
        self.steps = steps if steps is not None else [Step(explanation="Start.", expression="x")]
        self.fails_on = fails_on
        self.fails_with = fails_with or ValueError("Gemini returned no text")
        self.prompts: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        self.prompts.append(prompt)
        if schema.__name__ == self.fails_on:
            raise self.fails_with
        if schema is Extraction:
            return schema.model_validate(Extraction(sympy_code=self.sympy_code).model_dump())
        return schema.model_validate(Solution(steps=self.steps).model_dump())


def make_state(problem: str) -> PipelineState:
    return {
        "user_input": problem,
        "problem_statement": problem,
        "topic": "algebra",
        "difficulty": "school",
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


def test_solver_solves_a_problem_sympy_can_handle():
    llm = FakeLLM(
        sympy_code="result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))",
        steps=[
            Step(explanation="Start from the equation.", expression="Eq(x**2 - 4, 0)"),
            Step(explanation="Add four to both sides.", expression="Eq(x**2, 4)"),
        ],
    )

    state = solver_node(make_state("Solve x**2 - 4 = 0"), llm)

    assert state["solvable"] is True
    assert state["error"] is None
    assert len(state["solution"]) == 2


def test_solver_reports_the_error_when_the_sympy_code_raises():
    llm = FakeLLM(sympy_code="result = sp.solve(")

    state = solver_node(make_state("Draw me a house"), llm)

    assert state["solvable"] is False
    assert state["solution"] == []
    assert state["error"] is not None
    assert "sympy could not evaluate this problem" in state["error"]


def test_solver_reports_the_error_when_the_code_sets_no_result():
    llm = FakeLLM(sympy_code="x = 1")

    state = solver_node(make_state("What is beauty?"), llm)

    assert state["solvable"] is False
    assert state["error"] is not None
    assert "sympy produced no result" in state["error"]


def test_solver_gives_up_on_steps_it_cannot_parse():
    llm = FakeLLM(
        sympy_code="result = sp.Integer(2)",
        steps=[Step(explanation="Nonsense.", expression="Eq(x, )")],
    )

    state = solver_node(make_state("Solve x = 2"), llm)

    assert state["solvable"] is False
    assert state["error"] is not None
    assert "could not be parsed" in state["error"]
    # One extraction call plus one call per explanation attempt.
    assert len(llm.prompts) == 1 + MAX_EXPLANATION_ATTEMPTS


def test_solver_error_tells_the_user_how_to_rephrase():
    llm = FakeLLM(sympy_code="result = sp.solve(")

    state = solver_node(make_state("Draw me a house"), llm)

    assert state["error"] is not None
    assert "more explicitly" in state["error"]


def test_solver_clears_an_error_from_an_earlier_run():
    llm = FakeLLM(sympy_code="result = sp.Integer(2)")
    state = make_state("Solve x = 2")
    state["error"] = "left over from a previous run"

    assert solver_node(state, llm)["error"] is None


def test_solver_reports_the_error_when_the_extraction_call_fails():
    llm = FakeLLM(sympy_code="result = sp.Integer(2)", fails_on="Extraction")

    state = solver_node(make_state("Solve x = 2"), llm)

    assert state["solvable"] is False
    assert state["error"] is not None
    assert "Could not extract the math from this problem" in state["error"]
    assert "more explicitly" in state["error"]


def test_solver_reports_the_error_when_the_candidate_generation_call_fails():
    llm = FakeLLM(sympy_code="result = sp.Integer(2)", fails_on="Solution")

    state = solver_node(make_state("Solve x = 2"), llm)

    assert state["solvable"] is False
    assert state["solution"] == []
    assert state["error"] is not None
    assert "Could not generate a solution for this problem" in state["error"]
    assert "more explicitly" in state["error"]
    # The LLM call itself failing is not "this candidate was bad" — it ends
    # the node immediately rather than retrying with a different candidate.
    assert len(llm.prompts) == 2


def test_solver_reports_an_api_error_on_extraction_without_the_rephrase_hint():
    llm = FakeLLM(
        sympy_code="result = sp.Integer(2)",
        fails_on="Extraction",
        fails_with=LLMUnavailableError("429 RESOURCE_EXHAUSTED"),
    )

    state = solver_node(make_state("Solve x = 2"), llm)

    assert state["solvable"] is False
    assert state["error"] is not None
    assert "Could not reach the AI service" in state["error"]
    assert "more explicitly" not in state["error"]


def test_solver_reports_an_api_error_on_candidate_generation_without_the_rephrase_hint():
    llm = FakeLLM(
        sympy_code="result = sp.Integer(2)",
        fails_on="Solution",
        fails_with=LLMUnavailableError("429 RESOURCE_EXHAUSTED"),
    )

    state = solver_node(make_state("Solve x = 2"), llm)

    assert state["solvable"] is False
    assert state["solution"] == []
    assert state["error"] is not None
    assert "Could not reach the AI service" in state["error"]
    assert "more explicitly" not in state["error"]
