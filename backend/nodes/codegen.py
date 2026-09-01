"""codegen_node — turn planned scenes into runnable Manim scene code. Scaffold
and objects are generated deterministically; only the animation calls
inside `construct()` come from the LLM.
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
ANIMATION_SECONDS = 1.0  # Manim's default animation duration
MIN_PAUSE_SECONDS = 0.4  # shortest pause a viewer can still read

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
    """Collect the solution-step expressions a scene covers. `step_indices`
    is 1-based, `state["solution"]` is 0-based."""
    return [state["solution"][index - 1].expression for index in scene.step_indices]


def _to_latex(expression: str) -> str:
    """Render a sympy expression as LaTeX, exactly as written: unevaluated so
    manipulations stay visible, `order="none"` so terms keep their position.
    """
    return sp.latex(sp.sympify(expression, evaluate=False), order="none")


def _quote(value: str) -> str:
    """JSON-quote a string for embedding in generated Python source, so
    backslash-heavy LaTeX survives round-tripping through a source file."""
    return json.dumps(value)


def _wrap(narration: str) -> str:
    """Break narration into subtitle lines of roughly equal length, keeping
    the subtitle at a constant font size."""
    return "\n".join(textwrap.wrap(narration, width=SUBTITLE_LINE_LENGTH))


def _indent(code: str) -> str:
    """Indent generated statements to sit inside `construct()`."""
    return "\n".join(f"        {line}" if line.strip() else "" for line in code.splitlines())


def _split_latex(latex: str) -> list[str]:
    """Split a LaTeX expression at its top-level `+`, `-` and `=` signs, so
    each term is addressable via `get_part_by_tex`. Nested braces, `\\left...
    \\right` pairs and `\\frac` are left intact.
    """
    parts: list[str] = []
    current = ""
    depth = 0
    index = 0

    while index < len(latex):
        char = latex[index]

        if char == "\\":
            end = index + 1  # copy the control sequence whole
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
    """Find the first expression plottable as y = f(x), with its free symbol."""
    for expression in expressions:
        parsed = sp.sympify(expression)
        if not isinstance(parsed, sp.Expr) or parsed.is_number:
            continue
        symbols = parsed.free_symbols
        if len(symbols) == 1:
            return parsed, symbols.pop()
    return None


def _setup_formulas(latex_formulas: list[str]) -> tuple[str, dict[str, list[str]]]:
    """Create one `MathTex` per formula, centred and built from its terms."""
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
    "geometry"/"diagram" fall back to formulas, since `Scene` carries no
    points/edges to draw a construction or tree from.
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
    """Ask the LLM for the scene's animation calls, retrying on invalid code,
    falling back to `_default_animation` after `MAX_ANIMATION_ATTEMPTS`."""
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
    Animations are never shortened; `assembler_node` pads the audio if the
    animations still outlast the narration.
    """
    lines = body.splitlines()
    animations = sum(1 for line in lines if PLAY_CALL.match(line))
    pauses = [index for index, line in enumerate(lines) if WAIT_CALL.match(line)]
    if not pauses:
        return body

    animation_seconds = animations * ANIMATION_SECONDS
    shortest = animation_seconds + len(pauses) * MIN_PAUSE_SECONDS
    target = max(narration_seconds, shortest)
    pause = whole_frames((target - animation_seconds) / len(pauses))
    written = math.ceil(pause * 10_000) / 10_000  # rounded up, stays on the frame boundary

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


def fallback_code(scene: Scene, narration_seconds: float) -> str:
    """Build a title-only scene, with no LaTeX or generated animation left to
    fail, for `executor_node` to fall back to."""
    setup, objects = _setup_title(scene)
    scaffold = SCENE_TEMPLATE.format(
        extra_imports="",
        class_name=f"Scene{scene.number}",
        narration=_quote(_wrap(scene.narration)),
        setup=setup,
        animation_body=ANIMATION_PLACEHOLDER,
    )
    body = _fit_timing(_indent(_default_animation(objects)), narration_seconds)

    return scaffold.replace(ANIMATION_PLACEHOLDER, body)


def codegen_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Generate Manim code for every planned scene."""
    state["manim_codes"] = [
        _render_scene(state, scene, llm, narration_seconds)
        for scene, narration_seconds in zip(state["scenes"], state["scene_durations"])
    ]

    return state
