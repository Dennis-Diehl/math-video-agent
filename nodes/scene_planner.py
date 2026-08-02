from config.llm.base import BaseLLM
from config.schemas import ScenePlan
from graph.pipeline_state import PipelineState

SCENE_PLANNER_SYSTEM_PROMPT = """You are a video director grouping a step-by-step math solution \
into video scenes.

### Rules
- Group the given steps into scenes — you do not have to use a 1:1 mapping; combine steps that \
belong together into one scene, or split a dense step into multiple scenes, whatever makes for \
clearer, better-paced scenes.
- `title` is a short descriptive title for the scene.
- `narration` is the spoken narration and subtitle text for the scene (may combine or rephrase \
the underlying steps' explanations into one flowing narration).
- `animation_steps` are short descriptions of what visually happens in the scene, e.g. \
"Show the equation x**2 - 4 = 0", "Transform it into (x-2)*(x+2) = 0", "Highlight both factors".
- `visual_type` is one of "graph", "equation", "geometry", "diagram", "table", "text". Use:
  - `"graph"` for anything plotted on a coordinate system/axis (function plots, probability \
distributions).
  - `"equation"` for any scene showing mathematical notation (formulas, matrices, symbolic \
steps) without a plot or shape.
  - `"geometry"` for concrete geometric objects with measurements/construction (triangles, \
circles, angles).
  - `"diagram"` for abstract, non-metric structures without axes (probability trees, Venn \
diagrams, flowcharts).
  - `"table"` for tabular data (value tables, truth tables) shown to help solve the problem.
  - `"text"` only for scenes with no mathematical notation, plot, or shape at all.

### Output Format
A list of scenes, each with a sequential `number` (starting at 1), a `title`, `narration`, \
`visual_type`, and `animation_steps`."""


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
        prompt=f"Group the following solution steps into a video scene plan:\n\n{steps_text}",
        schema=ScenePlan,
        system_prompt=SCENE_PLANNER_SYSTEM_PROMPT,
    )

    state["scenes"] = scene_plan.scenes

    return state
