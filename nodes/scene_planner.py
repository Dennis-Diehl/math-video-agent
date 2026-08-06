from config.llm.base import BaseLLM
from config.schemas import ScenePlan
from graph.pipeline_state import PipelineState

SCENE_PLANNER_SYSTEM_PROMPT = """You are a video director grouping a step-by-step math solution \
into video scenes.

### Rules
- `step_indices`: the 1-based input steps a scene covers, e.g. `[2, 3]`. Every step must be \
covered by exactly one scene, in order, no gaps or repeats.
- The steps come in pairs: an operation being carried out, then its tidied-up result. Keep such \
a pair in one scene — split across scenes, the manipulation becomes a cut and the viewer never \
sees it happen. Otherwise keep scenes small: two to three steps, never more than four.
- The first scene introduces the problem: `narration` welcomes the viewer and says what will be \
worked out, with the first step as its `step_indices`.
- `title`: a short descriptive title.
- `narration`: the spoken and subtitle text, combining or rephrasing the steps' explanations. It \
is read aloud, so spell mathematics out — "x squared minus four equals zero", never `x^2 - 4 = \
0` or any `^`, `**`, `*`, `sqrt` notation.
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
    """Generate a plan for a math video, given a solution to a math problem.

    Args:
        state: The current pipeline state.
        llm: The LLM to use for generating the scene plan.

    Returns:
        Updated pipeline state with `scenes` set.
    """

    steps_text = "\n".join(
        f"{i + 1}. {step.explanation} ({step.expression})"
        for i, step in enumerate(state["solution"])
    )

    scene_plan: ScenePlan = llm.generate_structured(
        prompt=(
            f"Problem the video explains: '{state['problem_statement']}'\n\n"
            f"Group the following solution steps into a video scene plan:\n\n{steps_text}"
        ),
        schema=ScenePlan,
        system_prompt=SCENE_PLANNER_SYSTEM_PROMPT,
    )

    state["scenes"] = scene_plan.scenes

    return state
