"""codegen_node — turn planned scenes into runnable Manim scene code.

Each scene is built from a fixed scaffold: the class definition, the subtitle
and the Manim objects a scene needs (formulas, axes, tables) are generated
deterministically, so the objects on screen always carry the exact expressions
that were already validated in `solver_node`. Only the animation calls inside
`construct()` come from the LLM, which turns the scene's free-text
`animation_steps` into `self.play(...)` lines over those pre-built objects.
"""

import json
import textwrap

import sympy as sp

from config.llm.base import BaseLLM
from config.schemas import AnimationCode, Scene
from graph.pipeline_state import PipelineState

MAX_ANIMATION_ATTEMPTS = 3

ANIMATION_PLACEHOLDER = "___ANIMATION_BODY___"

ANIMATION_SYSTEM_PROMPT = """You are a Manim animator writing the animation calls for one scene \
of a math explanation video.

### Rules
- The scene class, its `construct()` method, the subtitle and every Manim object already exist. \
Write only the animation calls that belong inside `construct()`.
- The objects exist but are not on screen yet. Every object you animate must first be brought in \
with `Write`, `Create` or `FadeIn`.
- Only use the objects listed as available, spelled exactly as listed. Never create, rename or \
redefine an object, never index into one (no `formula_1[0]`), and never reference a name that is \
not in the list.
- Use only `self.play(...)` and `self.wait(...)` statements, one statement per line, with no \
leading indentation.
- Use only these animations: `Write`, `Create`, `Transform`, `Indicate`, `Circumscribe`, \
`FadeIn`, `FadeOut`.
- Use `Write` for text and formulas, `Create` for axes, graphs and tables.
- `Transform(a, b)` morphs `a` into `b` and leaves `b` off screen, so never bring `b` in \
separately, and keep referring to `a` afterwards.
- Highlight an object that is already on screen with `Indicate(obj)` or `Circumscribe(obj)`, \
never by changing its color.
- Work through the requested animation steps in order, using one or more statements per step, \
and follow each step with `self.wait(1)`.
- Do not import anything, do not define functions, classes or variables, do not write comments, \
and do not wrap the output in markdown code fences.

### Output Format
Plain Python statements, one per line, without indentation. For a scene with the objects \
`formula_1, formula_2` and the steps "Show the equation" and "Rewrite it in factored form":
self.play(Write(formula_1))
self.wait(1)
self.play(Transform(formula_1, formula_2))
self.wait(1)"""

SUBTITLE_LINE_LENGTH = 60

SCENE_TEMPLATE = """from manim import *
{extra_imports}

class {class_name}(Scene):
    def construct(self):
        subtitle = Text({narration}, font_size=24, line_spacing=0.6)
        if subtitle.width > 13:
            subtitle.scale_to_fit_width(13)
        subtitle.to_edge(DOWN)
        self.add(subtitle)

{setup}

{animation_body}
"""


def _scene_expressions(state: PipelineState, scene: Scene) -> list[str]:
    """Collect the solution-step expressions a scene covers.

    `Scene.step_indices` is 1-based (it refers to the numbering the scene
    planner saw), while `state["solution"]` is a 0-based list.
    """
    return [state["solution"][index - 1].expression for index in scene.step_indices]


def _to_latex(expression: str) -> str:
    """Render a sympy expression string as LaTeX."""
    return sp.latex(sp.sympify(expression))


def _quote(value: str) -> str:
    """Quote a string for embedding in generated Python source.

    Uses JSON escaping so backslash-heavy LaTeX (`\\frac`, `\\left`) survives
    being written into a source file and parsed back by Python.
    """
    return json.dumps(value)


def _wrap(narration: str) -> str:
    """Break narration into subtitle lines of roughly equal length.

    Wrapping keeps the subtitle at a constant font size; scaling a long
    single line down to fit the frame would instead shrink the text of
    every wordier scene.
    """
    return "\n".join(textwrap.wrap(narration, width=SUBTITLE_LINE_LENGTH))


def _indent(code: str) -> str:
    """Indent generated statements to sit inside `construct()`."""
    return "\n".join(f"        {line}" if line.strip() else "" for line in code.splitlines())


def _plottable(expressions: list[str]) -> tuple[sp.Expr, sp.Symbol] | None:
    """Find the first expression that can be plotted as y = f(x).

    Returns the expression and its single free symbol, or `None` if no
    expression qualifies (multiple unknowns, a solution set, an equation).
    """
    for expression in expressions:
        parsed = sp.sympify(expression)
        if not isinstance(parsed, sp.Expr) or parsed.is_number:
            continue
        symbols = parsed.free_symbols
        if len(symbols) == 1:
            return parsed, symbols.pop()
    return None


def _setup_formulas(latex_formulas: list[str]) -> tuple[str, list[str]]:
    """Create one `MathTex` per formula, stacked at the top of the frame."""
    lines = []
    names = []
    for position, latex in enumerate(latex_formulas, start=1):
        name = f"formula_{position}"
        lines.append(f"{name} = MathTex({_quote(latex)}).to_edge(UP)")
        names.append(name)
    return _indent("\n".join(lines)), names


def _setup_graph(expression: sp.Expr, variable: sp.Symbol) -> tuple[str, list[str]]:
    """Create axes on the left, the formula on the right, and the curve."""
    lines = [
        "axes = Axes(x_range=[-5, 5, 1], y_range=[-5, 5, 1], x_length=6, y_length=5)",
        "axes.to_edge(LEFT)",
        f'axis_labels = axes.get_axis_labels(x_label="{variable.name}", y_label="y")',
        f"formula_1 = MathTex({_quote(sp.latex(expression))}).scale(0.8).to_edge(RIGHT)",
        f"graph = axes.plot(lambda {variable.name}: {sp.pycode(expression)}, color=BLUE)",
    ]
    return _indent("\n".join(lines)), ["axes", "axis_labels", "formula_1", "graph"]


def _setup_table(latex_formulas: list[str]) -> tuple[str, list[str]]:
    """Create a table with one expression per row."""
    rows = json.dumps([[latex] for latex in latex_formulas])
    lines = [
        f"table = MathTable({rows}, include_outer_lines=True)",
        "table.scale(0.6).to_edge(UP)",
    ]
    return _indent("\n".join(lines)), ["table"]


def _setup_title(scene: Scene) -> tuple[str, list[str]]:
    """Create a plain title for scenes without any mathematical notation."""
    return _indent(f"title = Text({_quote(scene.title)}, font_size=40).to_edge(UP)"), ["title"]


def _build_setup(scene: Scene, expressions: list[str]) -> tuple[str, list[str], str]:
    """Build a scene's object setup, its object names, and any extra imports.

    "geometry" and "diagram" fall back to showing formulas: drawing a
    construction or a tree needs points/edges that no field on `Scene` carries.
    """
    latex_formulas = [_to_latex(expression) for expression in expressions]

    if scene.visual_type == "text" or not latex_formulas:
        setup, names = _setup_title(scene)
        return setup, names, ""

    if scene.visual_type == "graph":
        plottable = _plottable(expressions)
        if plottable is not None:
            setup, names = _setup_graph(*plottable)
            return setup, names, "import math\n"

    if scene.visual_type == "table":
        setup, names = _setup_table(latex_formulas)
        return setup, names, ""

    setup, names = _setup_formulas(latex_formulas)
    return setup, names, ""


def _default_animation(object_names: list[str]) -> str:
    """Show every object in turn — used when the LLM cannot produce valid code."""
    lines = []
    for name in object_names:
        lines += [f"self.play(Write({name}))", "self.wait(1)"]
    return "\n".join(lines)


def _animation_prompt(scene: Scene, object_names: list[str]) -> str:
    steps = "\n".join(
        f"{position}. {step}" for position, step in enumerate(scene.animation_steps, 1)
    )
    return (
        f"Scene title: {scene.title}\n"
        f"Narration: {scene.narration}\n"
        f"Available objects: {', '.join(object_names)}\n"
        f"Animation steps to perform:\n{steps}"
    )


def _generate_animation(llm: BaseLLM, scene: Scene, object_names: list[str], scaffold: str) -> str:
    """Ask the LLM for the scene's animation calls, retrying on invalid code.

    The generated statements are compiled together with the scene scaffold, so
    syntax errors are caught here instead of surfacing during rendering. After
    `MAX_ANIMATION_ATTEMPTS` failures the scene falls back to simply showing
    each object.
    """
    prompt = _animation_prompt(scene, object_names)

    for _ in range(MAX_ANIMATION_ATTEMPTS):
        animation: AnimationCode = llm.generate_structured(
            prompt=prompt,
            schema=AnimationCode,
            system_prompt=ANIMATION_SYSTEM_PROMPT,
        )
        body = _indent(animation.code)
        try:
            compile(scaffold.replace(ANIMATION_PLACEHOLDER, body), "<scene>", "exec")
        except SyntaxError as error:
            prompt = (
                f"{_animation_prompt(scene, object_names)}\n"
                f"Your previous attempt was not valid Python: {error}\n"
                "Write the animation calls again, fixing the syntax."
            )
            continue
        return body

    return _indent(_default_animation(object_names))


def _render_scene(state: PipelineState, scene: Scene, llm: BaseLLM) -> str:
    """Build one scene's Manim module: fixed scaffold plus generated animations."""
    expressions = _scene_expressions(state, scene)
    setup, object_names, extra_imports = _build_setup(scene, expressions)

    scaffold = SCENE_TEMPLATE.format(
        extra_imports=extra_imports,
        class_name=f"Scene{scene.number}",
        narration=_quote(_wrap(scene.narration)),
        setup=setup,
        animation_body=ANIMATION_PLACEHOLDER,
    )
    body = _generate_animation(llm, scene, object_names, scaffold)

    return scaffold.replace(ANIMATION_PLACEHOLDER, body)


def codegen_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Generate Manim code for every planned scene.

    Args:
        state: Current pipeline state (reads `scenes` and `solution`).
        llm: LLM client used to turn each scene's `animation_steps` into
            Manim animation calls.

    Returns:
        Updated pipeline state with `manim_codes` set, one entry per scene.
    """
    state["manim_codes"] = [_render_scene(state, scene, llm) for scene in state["scenes"]]

    return state
