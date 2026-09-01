from config.llm.base import BaseLLM, T
from config.schemas import Extraction, Solution, Step
from graph.pipeline_state import PipelineState
from nodes.solver import MAX_EXPLANATION_ATTEMPTS, solver_node


class FakeLLM(BaseLLM):
    """A `BaseLLM` returning canned sympy code and solution steps.

    `solver_node` calls it twice with different schemas: once for `Extraction`,
    then repeatedly for `Solution`. The schema decides which canned answer to
    hand back, so a test only has to state the two it cares about.
    """

    def __init__(self, sympy_code: str, steps: list[Step] | None = None):
        self.sympy_code = sympy_code
        self.steps = steps if steps is not None else [Step(explanation="Start.", expression="x")]
        self.prompts: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        self.prompts.append(prompt)
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
