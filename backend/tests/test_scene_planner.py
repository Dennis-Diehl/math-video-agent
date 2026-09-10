from config.llm.base import BaseLLM, T
from config.schemas import Scene, ScenePlan, Step
from graph.pipeline_state import PipelineState
from nodes.scene_planner import scene_planner_node


class FakeLLM(BaseLLM):
    """A `BaseLLM` returning a canned scene plan, or raising if told to."""

    def __init__(self, scene_plan: ScenePlan | None = None, raises: Exception | None = None):
        self.scene_plan = scene_plan or ScenePlan(
            scenes=[
                Scene(
                    number=1,
                    title="Solving",
                    narration="We add four to both sides.",
                    visual_type="equation",
                    animation_steps=["Show the equation"],
                    step_indices=[1, 2],
                )
            ]
        )
        self.raises = raises

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        if self.raises is not None:
            raise self.raises
        return schema.model_validate(self.scene_plan.model_dump())


def make_state(problem: str) -> PipelineState:
    return {
        "user_input": problem,
        "problem_statement": problem,
        "topic": "algebra",
        "difficulty": "school",
        "solution": [
            Step(explanation="Start.", expression="Eq(x**2 - 4, 0)"),
            Step(explanation="Add four.", expression="Eq(x**2, 4)"),
        ],
        "solvable": True,
        "scenes": [],
        "manim_codes": [],
        "scene_videos": [],
        "audio_files": [],
        "scene_durations": [],
        "final_video": "",
        "error": None,
    }


def test_scene_planner_plans_scenes_from_the_solution():
    llm = FakeLLM()

    state = scene_planner_node(make_state("Solve x**2 - 4 = 0"), llm)

    assert state["error"] is None
    assert len(state["scenes"]) == 1
    assert state["scenes"][0].title == "Solving"


def test_scene_planner_reports_the_error_when_the_llm_call_fails():
    llm = FakeLLM(raises=ValueError("Gemini returned no text"))

    state = scene_planner_node(make_state("Solve x**2 - 4 = 0"), llm)

    assert state["scenes"] == []
    assert state["error"] is not None
    assert "Could not plan the animation for this solution" in state["error"]


def test_scene_planner_error_does_not_suggest_rephrasing():
    llm = FakeLLM(raises=ValueError("Gemini returned no text"))

    state = scene_planner_node(make_state("Solve x**2 - 4 = 0"), llm)

    assert state["error"] is not None
    assert "more explicitly" not in state["error"]


def test_scene_planner_clears_an_error_from_an_earlier_run():
    llm = FakeLLM()
    state = make_state("Solve x**2 - 4 = 0")
    state["error"] = "left over from a previous run"

    assert scene_planner_node(state, llm)["error"] is None
