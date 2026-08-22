import math
import re

import pytest

from config.llm.base import BaseLLM, T
from config.schemas import AnimationCode, Scene, Step
from graph.media import FRAMES_PER_SECOND
from graph.pipeline_state import PipelineState
from nodes.codegen import (
    ANIMATION_SECONDS,
    MAX_ANIMATION_ATTEMPTS,
    MIN_PAUSE_SECONDS,
    _fit_timing,
    codegen_node,
)


class FakeLLM(BaseLLM):
    """A `BaseLLM` that returns canned animation code and records its prompts."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.prompts: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        self.prompts.append(prompt)
        code = self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]
        return schema.model_validate(AnimationCode(code=code).model_dump())


def make_state(scenes: list[Scene]) -> PipelineState:
    return {
        "user_input": "solve x^2-4=0 pls",
        "problem_statement": "Solve the equation x**2 - 4 = 0.",
        "topic": "algebra",
        "difficulty": "school",
        "solution": [
            Step(explanation="Start.", expression="Eq(x**2 - 4, 0)"),
            Step(explanation="Factor.", expression="Eq((x - 2)*(x + 2), 0)"),
        ],
        "solvable": True,
        "scenes": scenes,
        # One narration length per scene: codegen times each scene to its words.
        "scene_durations": [5.0] * len(scenes),
        "manim_codes": [],
        "scene_videos": [],
        "audio_files": [],
        "error": None,
    }


def make_scene(**overrides: object) -> Scene:
    fields: dict[str, object] = {
        "number": 1,
        "title": "Factoring",
        "narration": "We factor the equation.",
        "visual_type": "equation",
        "animation_steps": ["Show the equation"],
        "step_indices": [1, 2],
    }
    fields.update(overrides)
    return Scene(**fields)  # type: ignore[arg-type]


def test_codegen_writes_one_code_per_scene():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    state = make_state([make_scene(number=1), make_scene(number=2)])

    state = codegen_node(state, llm)

    assert len(state["manim_codes"]) == 2
    assert "class Scene1(Scene):" in state["manim_codes"][0]
    assert "class Scene2(Scene):" in state["manim_codes"][1]


def test_codegen_renders_validated_expressions_as_latex():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    state = make_state([make_scene()])

    code = codegen_node(state, llm)["manim_codes"][0]

    # The LaTeX comes from the solution steps, not from the LLM, and each
    # formula is split into terms so single terms can be highlighted.
    assert 'formula_1 = MathTex("x^{2}", "- 4", "= 0")' in code
    assert "formula_2 = MathTex(" in code


def test_codegen_resolves_step_indices_one_based():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    state = make_state([make_scene(step_indices=[2])])

    code = codegen_node(state, llm)["manim_codes"][0]

    # step_indices=[2] must pick the second step, not the third or the first.
    assert "x^{2} - 4 = 0" not in code
    assert "formula_2" not in code


def test_codegen_embeds_generated_animation_calls():
    llm = FakeLLM(["self.play(Write(formula_1))\nself.wait(1)"])
    state = make_state([make_scene()])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "        self.play(Write(formula_1))" in code
    # The pause is rewritten to make the scene last as long as its narration:
    # 5s of words minus 1s of animation leaves 4s to wait.
    assert "        self.wait(4.0000)" in code


def test_codegen_passes_available_objects_and_their_terms_to_llm():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    state = make_state([make_scene()])

    codegen_node(state, llm)

    prompt = llm.prompts[0]
    assert "formula_1" in prompt
    assert "formula_2" in prompt
    # The addressable terms must be listed, otherwise get_part_by_tex is a guess.
    assert '"x^{2}"' in prompt
    assert '"- 4"' in prompt


def test_codegen_retries_when_generated_code_has_a_syntax_error():
    llm = FakeLLM(["self.play(Write(formula_1)", "self.play(Write(formula_1))"])
    state = make_state([make_scene()])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert len(llm.prompts) == 2
    assert "not valid Python" in llm.prompts[1]
    assert "        self.play(Write(formula_1))" in code


def test_codegen_falls_back_after_exhausting_attempts():
    llm = FakeLLM(["this is not python at all ("])
    state = make_state([make_scene()])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert len(llm.prompts) == MAX_ANIMATION_ATTEMPTS
    # The fallback simply shows every object that was set up.
    assert "self.play(Write(formula_1))" in code
    assert "self.play(Write(formula_2))" in code


def test_codegen_wraps_long_narration_instead_of_scaling_it():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    narration = (
        "To isolate the term with x, we subtract six from both sides of the "
        "equation, leaving us with three x equals negative six."
    )
    state = make_state([make_scene(narration=narration)])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "\\n" in code.split("subtitle = Text(")[1].split(", font_size")[0]


def test_codegen_builds_axes_for_a_plottable_graph_scene():
    llm = FakeLLM(["self.play(Create(axes))"])
    state = make_state([make_scene(visual_type="graph", step_indices=[1])])
    state["solution"] = [Step(explanation="The parabola.", expression="x**2 - 4")]

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "axes = Axes(" in code
    assert "axes.plot(lambda x: x**2 - 4" in code


def test_codegen_falls_back_to_formulas_when_graph_is_not_plottable():
    llm = FakeLLM(["self.play(Write(formula_1))"])
    # An equation in two unknowns is not a single-variable function.
    state = make_state([make_scene(visual_type="graph", step_indices=[1])])
    state["solution"] = [Step(explanation="Two unknowns.", expression="Eq(x + y, 4)")]

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "axes = Axes(" not in code
    assert "formula_1 = MathTex(" in code


def test_codegen_builds_a_table_for_a_table_scene():
    llm = FakeLLM(["self.play(Create(table))"])
    state = make_state([make_scene(visual_type="table")])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "table = MathTable(" in code


def test_codegen_builds_a_title_for_a_text_scene():
    llm = FakeLLM(["self.play(Write(title))"])
    state = make_state([make_scene(visual_type="text")])

    code = codegen_node(state, llm)["manim_codes"][0]

    assert "title = Text(" in code
    assert "MathTex(" not in code


def test_codegen_generated_code_is_syntactically_valid():
    llm = FakeLLM(["self.play(Write(formula_1))\nself.wait(1)"])
    state = make_state([make_scene()])

    code = codegen_node(state, llm)["manim_codes"][0]

    compile(code, "<scene>", "exec")


def test_split_latex_keeps_nested_structure_intact():
    from nodes.codegen import _split_latex

    # Top-level operators split, nested ones do not.
    assert _split_latex("x^{2} - 4 = 0") == ["x^{2}", "- 4", "= 0"]
    # The exponent's minus must survive, it is what shows the power rule.
    assert _split_latex("3 x^{3 - 1} + 2") == ["3 x^{3 - 1}", "+ 2"]
    # Matrices and \left...\right groups stay whole.
    matrix = r"\left[\begin{matrix}2 & 1\\1 & 2\end{matrix}\right]"
    assert _split_latex(matrix) == [matrix]
    assert _split_latex(r"\frac{d}{d x} \left(x^{3} + 2 x\right)") == [
        r"\frac{d}{d x} \left(x^{3} + 2 x\right)"
    ]


def test_split_latex_is_lossless():
    from nodes.codegen import _split_latex

    for latex in [
        "x^{2} - 4 + 4 = 0 + 4",
        r"\left(x - 2\right) \left(x + 2\right) = 0",
        r"\frac{1}{2} x + 3",
        r"\int \left(2 x + 1\right)\, dx",
    ]:
        assert "".join(_split_latex(latex)).replace(" ", "") == latex.replace(" ", "")


def test_to_latex_keeps_the_order_the_solver_wrote():
    from nodes.codegen import _to_latex

    # sympy's default latex() sorts terms into its own canonical order, which
    # would swap terms between consecutive steps for no visible reason.
    assert _to_latex("Derivative(x**3, x) + Derivative(2*x, x)") == (
        r"\frac{d}{d x} x^{3} + \frac{d}{d x} 2 x"
    )
    assert _to_latex("(x - 2)*(x + 2)") == r"\left(x - 2\right) \left(x + 2\right)"
    assert _to_latex("2*x**(1 + 1)/(1 + 1) + x").startswith(r"\frac{2 x^{1 + 1}}{1 + 1}")


def scene_seconds(code: str) -> float:
    """How long a generated scene runs: one second per animation plus its pauses."""
    animations = len(re.findall(r"self\.play\(", code))
    pauses = [float(value) for value in re.findall(r"self\.wait\(([\d.]+)\)", code)]
    return animations * ANIMATION_SECONDS + sum(pauses)


BODY = """self.play(Write(formula_1))
self.wait(1)
self.play(TransformMatchingTex(formula_1, formula_2))
self.wait(1)
self.play(Indicate(formula_2))
self.wait(1)"""


def test_fit_timing_matches_a_narration_longer_than_the_animations():
    fitted = _fit_timing(BODY, narration_seconds=9.0)

    assert scene_seconds(fitted) == pytest.approx(9.0, abs=0.05)


def test_fit_timing_stretches_the_pauses_not_the_animations():
    fitted = _fit_timing(BODY, narration_seconds=9.0)

    # Three animations stay at a second each; the extra six seconds go to the pauses.
    assert len(re.findall(r"self\.play\(", fitted)) == 3
    assert [float(v) for v in re.findall(r"self\.wait\(([\d.]+)\)", fitted)] == [2.0, 2.0, 2.0]


def test_fit_timing_never_rushes_animations_for_a_short_narration():
    # Squeezing three animations into 2.92s would hurry the very moment the
    # viewer needs to follow, so the scene stays longer than the words.
    fitted = _fit_timing(BODY, narration_seconds=2.92)

    assert len(re.findall(r"self\.play\(", fitted)) == 3
    assert scene_seconds(fitted) > 2.92


def test_fit_timing_keeps_every_pause_readable():
    fitted = _fit_timing(BODY, narration_seconds=0.1)

    pauses = [float(value) for value in re.findall(r"self\.wait\(([\d.]+)\)", fitted)]
    assert all(pause >= MIN_PAUSE_SECONDS for pause in pauses)


def test_fit_timing_leaves_a_body_without_pauses_alone():
    body = "self.play(Write(formula_1))"

    assert _fit_timing(body, narration_seconds=9.0) == body


def test_fit_timing_keeps_indentation():
    fitted = _fit_timing("        self.play(Write(f))\n        self.wait(1)", narration_seconds=5.0)

    assert fitted.splitlines()[1].startswith("        self.wait(")


def played_seconds(code: str) -> float:
    """How long Manim really runs a scene, counting whole frames only."""
    animations = len(re.findall(r"self\.play\(", code))
    pauses = [float(value) for value in re.findall(r"self\.wait\(([\d.]+)\)", code)]
    truncated = sum(math.floor(p * FRAMES_PER_SECOND) / FRAMES_PER_SECOND for p in pauses)
    return animations * ANIMATION_SECONDS + truncated


def test_fit_timing_pauses_survive_manims_frame_truncation():
    # Manim drops a partial frame, so a pause written as 0.53 becomes seven
    # frames instead of eight and the scene ends before the narration does.
    for narration in [2.92, 4.05, 5.30, 5.34, 6.7, 9.0]:
        fitted = _fit_timing(BODY, narration_seconds=narration)
        assert played_seconds(fitted) >= narration, f"scene ends early for {narration}s of speech"


def test_fit_timing_rounds_pauses_up_to_whole_frames():
    fitted = _fit_timing(BODY, narration_seconds=6.7)

    for value in re.findall(r"self\.wait\(([\d.]+)\)", fitted):
        frames = float(value) * FRAMES_PER_SECOND
        assert frames >= math.floor(frames) >= 1
        # Written high enough that truncating lands on the intended frame.
        assert math.floor(frames) == round(frames, 3) // 1
