"""codegen_node — turn planned scenes into runnable Manim scene code.

Each scene is built from a fixed scaffold: the class definition, the subtitle
and the Manim objects a scene needs (formulas, axes, tables) are generated
deterministically, so the objects on screen always carry the exact expressions
that were already validated in `solver_node`. Only the animation calls inside
`construct()` come from the LLM, which turns the scene's free-text
`animation_steps` into `self.play(...)` lines over those pre-built objects.
"""

import json
import math
import re
import textwrap

import sympy as sp

from config.llm.base import BaseLLM
from config.schemas import AnimationCode, Scene
from graph.media import whole_frames
from graph.pipeline_state import PipelineState

MAX_ANIMATION_ATTEMPTS = 3

# Manim plays an animation over one second unless told otherwise.
ANIMATION_SECONDS = 1.0

# The shortest pause that still lets a viewer read what changed.
MIN_PAUSE_SECONDS = 0.4

PLAY_CALL = re.compile(r"^\s*self\.play\(")
WAIT_CALL = re.compile(r"^(\s*)self\.wait\([^)]*\)\s*$")

ANIMATION_PLACEHOLDER = "___ANIMATION_BODY___"

ANIMATION_SYSTEM_PROMPT = """You write the animation calls for one scene of a Manim math video.

### Rules
- The scene class, the subtitle and every object already exist. Write only `self.play(...)` and \
`self.wait(...)` statements, one per line, no indentation, no imports, no comments, no markdown \
fences.
- Use only the listed objects, spelled exactly as listed: never create, rename or redefine one, \
and never address a part by position (no `formula_1[0]`).
- A formula is built from its individual terms, so `formula_1.get_part_by_tex("+ 4")` returns \
just that term. Use it to highlight the term that changed — the exact text of every term is \
listed with the object. Passing text that is not in that list makes the render fail.
- Objects are not on screen yet. Bring each one in with `Write` (text, formulas) or `Create` \
(axes, graphs, tables) before animating it.
- Allowed animations: `Write`, `Create`, `TransformMatchingTex`, `Indicate`, `Circumscribe`, \
`Flash`, `FadeIn`, `FadeOut`.
- `TransformMatchingTex(a, b)` replaces `a` with `b` on screen. Never bring `b` in separately \
first, and from then on refer to `b`, never to `a` again — a chain of three formulas is \
`TransformMatchingTex(formula_1, formula_2)` followed by \
`TransformMatchingTex(formula_2, formula_3)`. Referring back to an already replaced formula \
puts it back on screen on top of the current one.
- Every listed formula must appear on screen, and every consecutive pair must be joined by a \
`TransformMatchingTex`: with `formula_1, formula_2, formula_3` that is one `Write` and two \
transforms. Leaving a formula out drops the change that leads to it, and the viewer sees a cut \
where the working should be. This holds for the opening scene too — welcoming the viewer does \
not replace showing the first transformation.
- Make every change visible instead of cutting between pictures:
  - Bring multi-part scenes in one piece at a time (axes, then formula, then curve).
  - A scene holding a single object (a table, a graph, a title) has nothing to transform: bring \
it in, then highlight what the narration refers to.
  - After each change, point out what changed or what the narration refers to with `Indicate`, \
`Circumscribe` or `Flash` — never by changing colour — then `self.wait(1)`.
- Follow the requested steps in order, several statements per step. Prefer a richer animation \
over a minimal one.

### Output Format
Plain statements, one per line:
self.play(Write(formula_1))
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
    """Render a sympy expression string as LaTeX, exactly as it was written.

    Parsing is unevaluated so that a step showing an operation being carried
    out survives: `Eq(x**2 - 4 + 4, 0 + 4)` has to stay on screen as written
    instead of collapsing to `Eq(x**2, 4)`, which is what makes the
    manipulation visible to the viewer.

    `order="none"` keeps the terms where the solver put them. sympy otherwise
    sorts them into its own canonical order, which would silently swap terms
    between one step and the next — the viewer would see `d/dx x**3 + d/dx 2*x`
    turn into `d/dx 2*x + d/dx x**3` for no reason they could follow.
    """
    return sp.latex(sp.sympify(expression, evaluate=False), order="none")


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


def _split_latex(latex: str) -> list[str]:
    """Split a LaTeX expression at its top-level `+`, `-` and `=` signs.

    Building a `MathTex` from the pieces rather than one string makes each
    term addressable by content via `get_part_by_tex`, so an animation can
    highlight the term that just changed instead of the whole formula.

    Each operator stays attached to the term it introduces, and anything
    nested — braces, `\\left...\\right` pairs, `\\frac`, an exponent like
    `x^{3 - 1}` — is left intact.
    """
    parts: list[str] = []
    current = ""
    depth = 0
    index = 0

    while index < len(latex):
        char = latex[index]

        if char == "\\":
            # Copy a control sequence whole, so \left, \right and \frac are
            # never cut in the middle.
            end = index + 1
            while end < len(latex) and (latex[end].isalpha() or end == index + 1):
                end += 1
            token = latex[index:end]
            if token == r"\left":
                depth += 1
            elif token == r"\right":
                depth -= 1
            current += token
            index = end
            continue

        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1

        if depth == 0 and char in "+-=" and current.strip():
            parts.append(current.strip())
            current = char
            index += 1
            continue

        current += char
        index += 1

    if current.strip():
        parts.append(current.strip())

    return parts or [latex]


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


def _setup_formulas(latex_formulas: list[str]) -> tuple[str, dict[str, list[str]]]:
    """Create one `MathTex` per formula, centred in the frame.

    Each formula is built from its individual terms so that animations can
    address a single term with `get_part_by_tex`.
    """
    lines = []
    objects: dict[str, list[str]] = {}
    for position, latex in enumerate(latex_formulas, start=1):
        name = f"formula_{position}"
        terms = _split_latex(latex)
        joined = ", ".join(_quote(term) for term in terms)
        lines.append(f"{name} = MathTex({joined}).move_to(ORIGIN)")
        objects[name] = terms
    return _indent("\n".join(lines)), objects


def _setup_graph(expression: sp.Expr, variable: sp.Symbol) -> tuple[str, dict[str, list[str]]]:
    """Create axes on the left, the formula on the right, and the curve."""
    lines = [
        "axes = Axes(x_range=[-5, 5, 1], y_range=[-5, 5, 1], x_length=6, y_length=5)",
        "axes.to_edge(LEFT)",
        f'axis_labels = axes.get_axis_labels(x_label="{variable.name}", y_label="y")',
        f"formula_1 = MathTex({_quote(sp.latex(expression))}).scale(0.8).to_edge(RIGHT)",
        f"graph = axes.plot(lambda {variable.name}: {sp.pycode(expression)}, color=BLUE)",
    ]
    return _indent("\n".join(lines)), {"axes": [], "axis_labels": [], "formula_1": [], "graph": []}


def _setup_table(latex_formulas: list[str]) -> tuple[str, dict[str, list[str]]]:
    """Create a table with one expression per row."""
    rows = json.dumps([[latex] for latex in latex_formulas])
    lines = [
        f"table = MathTable({rows}, include_outer_lines=True)",
        "table.scale(0.6).move_to(ORIGIN)",
    ]
    return _indent("\n".join(lines)), {"table": []}


def _setup_title(scene: Scene) -> tuple[str, dict[str, list[str]]]:
    """Create a plain title for scenes without any mathematical notation."""
    setup = _indent(f"title = Text({_quote(scene.title)}, font_size=40).move_to(ORIGIN)")
    return setup, {"title": []}


def _build_setup(scene: Scene, expressions: list[str]) -> tuple[str, dict[str, list[str]], str]:
    """Build a scene's object setup, its objects, and any extra imports.

    The objects map each name to the terms it can be addressed by, which is
    empty for anything that is not a formula.

    "geometry" and "diagram" fall back to showing formulas: drawing a
    construction or a tree needs points/edges that no field on `Scene` carries.
    """
    latex_formulas = [_to_latex(expression) for expression in expressions]

    if scene.visual_type == "text" or not latex_formulas:
        setup, objects = _setup_title(scene)
        return setup, objects, ""

    if scene.visual_type == "graph":
        plottable = _plottable(expressions)
        if plottable is not None:
            setup, objects = _setup_graph(*plottable)
            return setup, objects, "import math\n"

    if scene.visual_type == "table":
        setup, objects = _setup_table(latex_formulas)
        return setup, objects, ""

    setup, objects = _setup_formulas(latex_formulas)
    return setup, objects, ""


def _default_animation(objects: dict[str, list[str]]) -> str:
    """Show every object in turn — used when the LLM cannot produce valid code."""
    lines = []
    for name in objects:
        lines += [f"self.play(Write({name}))", "self.wait(1)"]
    return "\n".join(lines)


def _describe_objects(objects: dict[str, list[str]]) -> str:
    """List the objects and, for formulas, the terms they can be addressed by."""
    described = []
    for name, terms in objects.items():
        if terms:
            joined = ", ".join(_quote(term) for term in terms)
            described.append(f"- {name}, made of the terms {joined}")
        else:
            described.append(f"- {name}")
    return "\n".join(described)


def _animation_prompt(scene: Scene, objects: dict[str, list[str]]) -> str:
    steps = "\n".join(
        f"{position}. {step}" for position, step in enumerate(scene.animation_steps, 1)
    )
    return (
        f"Scene title: {scene.title}\n"
        f"Narration: {scene.narration}\n"
        f"Available objects:\n{_describe_objects(objects)}\n"
        f"Animation steps to perform:\n{steps}"
    )


def _generate_animation(
    llm: BaseLLM, scene: Scene, objects: dict[str, list[str]], scaffold: str
) -> str:
    """Ask the LLM for the scene's animation calls, retrying on invalid code.

    The generated statements are compiled together with the scene scaffold, so
    syntax errors are caught here instead of surfacing during rendering. After
    `MAX_ANIMATION_ATTEMPTS` failures the scene falls back to simply showing
    each object.
    """
    prompt = _animation_prompt(scene, objects)

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
                f"{_animation_prompt(scene, objects)}\n"
                f"Your previous attempt was not valid Python: {error}\n"
                "Write the animation calls again, fixing the syntax."
            )
            continue
        return body

    return _indent(_default_animation(objects))


def _fit_timing(body: str, narration_seconds: float) -> str:
    """Stretch a scene's pauses so it lasts as long as its narration.

    Manim runs an animation for a second and the generated code pauses for
    another, giving a scene a fixed length regardless of what is being said.
    The pauses absorb the difference; animations are never shortened, since
    rushing them would hide the step the viewer has to follow. A scene whose
    animations outlast its narration therefore ends after the words, and
    `assembler_node` pads the audio to match.

    Args:
        body: The generated `self.play(...)` / `self.wait(...)` statements.
        narration_seconds: How long this scene's narration takes to say.

    Returns:
        The same statements with the pause durations rewritten.
    """
    lines = body.splitlines()
    animations = sum(1 for line in lines if PLAY_CALL.match(line))
    pauses = [index for index, line in enumerate(lines) if WAIT_CALL.match(line)]
    if not pauses:
        return body

    animation_seconds = animations * ANIMATION_SECONDS
    shortest = animation_seconds + len(pauses) * MIN_PAUSE_SECONDS
    target = max(narration_seconds, shortest)
    # Rounded up: Manim truncates a partial frame, cutting the scene short.
    pause = whole_frames((target - animation_seconds) / len(pauses))

    # Rounded up at the last digit so the printed value stays on its frame
    # boundary: writing 8/15 as "0.53" would truncate back to seven frames.
    written = math.ceil(pause * 10_000) / 10_000

    for index in pauses:
        indent = WAIT_CALL.match(lines[index]).group(1)  # type: ignore[union-attr]
        lines[index] = f"{indent}self.wait({written:.4f})"

    return "\n".join(lines)


def _render_scene(
    state: PipelineState, scene: Scene, llm: BaseLLM, narration_seconds: float
) -> str:
    """Build one scene's Manim module: fixed scaffold plus generated animations."""
    expressions = _scene_expressions(state, scene)
    setup, objects, extra_imports = _build_setup(scene, expressions)

    scaffold = SCENE_TEMPLATE.format(
        extra_imports=extra_imports,
        class_name=f"Scene{scene.number}",
        narration=_quote(_wrap(scene.narration)),
        setup=setup,
        animation_body=ANIMATION_PLACEHOLDER,
    )
    body = _fit_timing(_generate_animation(llm, scene, objects, scaffold), narration_seconds)

    return scaffold.replace(ANIMATION_PLACEHOLDER, body)


def codegen_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Generate Manim code for every planned scene.

    Args:
        state: Current pipeline state (reads `scenes`, `solution` and
            `scene_durations`, which times each scene to its narration).
        llm: LLM client used to turn each scene's `animation_steps` into
            Manim animation calls.

    Returns:
        Updated pipeline state with `manim_codes` set, one entry per scene.
    """
    state["manim_codes"] = [
        _render_scene(state, scene, llm, narration_seconds)
        for scene, narration_seconds in zip(state["scenes"], state["scene_durations"])
    ]

    return state
