from config.llm.base import BaseLLM
from config.schemas import ScenePlan
from graph.pipeline_state import PipelineState

SCENE_PLANNER_SYSTEM_PROMPT = """You are a video director grouping a step-by-step math solution \
into video scenes.

### Rules
- `step_indices`: the 1-based input steps a scene shows, e.g. `[2, 3]`. Go through the steps in \
order and leave no gaps: every step must appear in some scene.
- Scenes overlap by one step. A scene opens on the step the previous scene ended on and then \
carries out its own change, so `[1, 2]` is followed by `[2, 3]`, then `[3, 4]`. That repeated \
step is the picture the viewer is already looking at when the scene starts.
- Because of that overlap, every scene shows at least two steps, never one — a one-step scene \
has nothing to animate, so its change turns into a cut between scenes that the viewer never sees \
happen. Two steps is the norm, three at most, beyond that the narration becomes a wall of text.
- The last scene is the one that arrives at the final step, and the video ends there. Never add \
a closing scene holding only that step: it writes the result a second time right after the \
viewer watched it appear.
- The first scene introduces the problem: `narration` welcomes the viewer and says what will be \
worked out, starting from the first step.
- `title`: a short descriptive title.
- `narration`: the spoken and subtitle text, combining or rephrasing the steps' explanations. \
Keep it to one or two sentences — it is shown as a subtitle, so a long paragraph is unreadable. \
It is read aloud, so spell mathematics out — "x squared minus four equals zero", never \
`x^2 - 4 = 0` or any `^`, `**`, `*`, `sqrt` notation.
- `animation_steps`: what visually happens, detailed enough to follow the reasoning from the \
picture alone. Say what changes and what to emphasise — "Add 4 on both sides and highlight the \
new terms", not "Show the next equation". Applies to every `visual_type`: which curve is drawn \
and what is pointed out, which table row matters. For example:
  `["Show the equation x**2 - 4 = 0", "Add 4 to both sides, showing x**2 - 4 + 4 = 0 + 4",
    "Cancel -4 and +4 on the left, leaving x**2 = 4", "Highlight the isolated x**2"]`
- `visual_type`:
  - `"graph"` — plotted on axes (function plots, distributions).
  - `"equation"` — mathematical notation without a plot or shape (formulas, matrices).
  - `"geometry"` — concrete figures with measurements (triangles, circles, angles).
  - `"diagram"` — abstract structures without axes (probability trees, Venn diagrams).
  - `"table"` — tabular data (value tables, truth tables).
  - `"text"` — only when there is no notation, plot or shape at all.

### Output Format
A list of scenes, each with a sequential `number` (from 1), `title`, `narration`, \
`visual_type`, `animation_steps`, and `step_indices`."""


def scene_planner_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Group a solution's steps into a plan of video scenes."""
    steps_text = "\n".join(
        f"{i + 1}. {step.explanation} ({step.expression})"
        for i, step in enumerate(state["solution"])
    )

    try:
        scene_plan: ScenePlan = llm.generate_structured(
            prompt=(
                f"Problem the video explains: '{state['problem_statement']}'\n\n"
                f"Group the following solution steps into a video scene plan:\n\n{steps_text}"
            ),
            schema=ScenePlan,
            system_prompt=SCENE_PLANNER_SYSTEM_PROMPT,
        )
    except Exception as e:  # noqa: BLE001 — the LLM call can raise any exception type
        state["error"] = f"Could not plan the animation for this solution: {e}"
        return state

    state["scenes"] = scene_plan.scenes
    state["error"] = None

    return state
