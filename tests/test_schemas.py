import pytest
from pydantic import ValidationError

from config.schemas import Classification, Extraction, Scene, ScenePlan, Solution, Step


def test_classification_accepts_valid_values():
    classification = Classification(topic="algebra", difficulty="school")
    assert classification.topic == "algebra"
    assert classification.difficulty == "school"


def test_classification_rejects_invalid_topic():
    with pytest.raises(ValidationError):
        Classification(topic="not_a_real_topic", difficulty="school")


def test_classification_rejects_invalid_difficulty():
    with pytest.raises(ValidationError):
        Classification(topic="algebra", difficulty="not_a_real_difficulty")


def test_extraction_accepts_valid_values():
    extraction = Extraction(sympy_code="result = sp.solve(x**2 - 4, x)")
    assert extraction.sympy_code == "result = sp.solve(x**2 - 4, x)"


def test_extraction_rejects_missing_sympy_code():
    with pytest.raises(ValidationError):
        Extraction()


def test_step_accepts_valid_values():
    step = Step(explanation="We factor the expression.", expression="(x-2)*(x+2)")
    assert step.explanation == "We factor the expression."
    assert step.expression == "(x-2)*(x+2)"


def test_step_rejects_missing_explanation():
    with pytest.raises(ValidationError):
        Step(expression="(x-2)*(x+2)")


def test_step_rejects_missing_expression():
    with pytest.raises(ValidationError):
        Step(explanation="We factor the expression.")


def test_solution_accepts_valid_steps():
    solution = Solution(
        steps=[
            Step(explanation="First step.", expression="x**2 - 4"),
            Step(explanation="Second step.", expression="(x-2)*(x+2)"),
        ]
    )
    assert len(solution.steps) == 2
    assert solution.steps[0].expression == "x**2 - 4"


def test_solution_accepts_empty_steps():
    solution = Solution(steps=[])
    assert solution.steps == []


def test_solution_rejects_non_step_items():
    with pytest.raises(ValidationError):
        Solution(steps=["not a Step instance"])


def test_scene_accepts_valid_values():
    scene = Scene(
        number=1,
        title="Factoring",
        narration="We factor the expression.",
        visual_type="equation",
        animation_steps=["Show the equation", "Highlight the factors"],
        step_indices=[1, 2],
    )
    assert scene.number == 1
    assert scene.title == "Factoring"
    assert scene.narration == "We factor the expression."
    assert scene.visual_type == "equation"
    assert scene.animation_steps == ["Show the equation", "Highlight the factors"]
    assert scene.step_indices == [1, 2]


def test_scene_rejects_invalid_visual_type():
    with pytest.raises(ValidationError):
        Scene(
            number=1,
            title="Factoring",
            narration="We factor the expression.",
            visual_type="not_a_real_visual_type",
            animation_steps=["Show the equation"],
            step_indices=[1],
        )


def test_scene_rejects_missing_number():
    with pytest.raises(ValidationError):
        Scene(
            title="Factoring",
            narration="We factor the expression.",
            visual_type="equation",
            animation_steps=["Show the equation"],
            step_indices=[1],
        )


def test_scene_plan_accepts_valid_scenes():
    scene_plan = ScenePlan(
        scenes=[
            Scene(
                number=1,
                title="Factoring",
                narration="We factor the expression.",
                visual_type="equation",
                animation_steps=["Show the equation"],
                step_indices=[1],
            ),
        ]
    )
    assert len(scene_plan.scenes) == 1
    assert scene_plan.scenes[0].title == "Factoring"


def test_scene_plan_accepts_empty_scenes():
    scene_plan = ScenePlan(scenes=[])
    assert scene_plan.scenes == []


def test_scene_plan_rejects_non_scene_items():
    with pytest.raises(ValidationError):
        ScenePlan(scenes=["not a Scene instance"])
