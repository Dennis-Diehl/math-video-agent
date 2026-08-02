import sympy as sp

from config.llm.base import BaseLLM
from config.schemas import Extraction, Solution
from graph.pipeline_state import PipelineState

MAX_EXPLANATION_ATTEMPTS = 3

EXTRACTION_SYSTEM_PROMPT = """You are a math assistant that writes short sympy code snippets \
to solve math problems.

### Rules
- Write valid Python code using the `sympy` module, already imported as `sp`.
- Define any symbols you need first with `sp.symbols(...)` before using them.
- Always assign the final answer to a variable named `result`.
- Use the sympy function that matches the problem: `sp.solve` for equations/roots, \
`sp.diff` for derivatives, `sp.integrate` for integrals, `sp.limit` for limits, \
`sp.Matrix`/matrix methods for linear algebra, `sp.geometry` for geometry problems, etc.
- Write the code using valid sympy syntax:
  - Use `**` for exponentiation, never `^` (e.g. `x**2`, not `x^2` — `^` means XOR in Python).
  - Use `sp.Eq(lhs, rhs)` for equations, never Python's `==` (e.g. `sp.Eq(x**2, 4)`, not \
`x**2 == 4` — `==` only checks structural equality, it does not represent an equation).
  - Use `sp.Rational(a, b)` for exact fractions, never plain `/` between integers \
(e.g. `sp.Rational(1, 2)`, not `1/2`, which becomes a float `0.5`).
- Do not include imports, print statements, comments, or explanations — only the code needed \
to compute `result`.

### Output Format
A short Python code snippet that assigns the final answer to a variable named `result`."""


EXPLANATION_SYSTEM_PROMPT = """You are a math tutor creating a step-by-step video explanation \
of how to solve a math problem.

### Rules
- Break the solution into discrete steps building toward the final answer.
- Each step has an `explanation` (spoken narration and subtitle text shown in the video) and an \
`expression` (the mathematical expression at that point in the solution).
- Write `explanation` in short, natural sentences suitable for being read aloud — not dense \
textbook prose.
- Write `expression` as a plain sympy expression string, parsed later with `sp.sympify()` — do \
not prefix sympy names with `sp.` here (e.g. write `Derivative(x**2, x)`, not \
`sp.Derivative(x**2, x)`; `sp.sympify()` already recognizes sympy names directly and does not \
know `sp`).
- Use `**` for exponentiation, never `^` (e.g. `x**2`, not `x^2` — `^` means XOR in Python).
- Use `Eq(lhs, rhs)` for equations, never Python's `==` (e.g. `Eq(x**2, 4)`, not `x**2 == 4`).
- Use `Rational(a, b)` for exact fractions, never plain `/` between integers \
(e.g. `Rational(1, 2)`, not `1/2`, which becomes a float `0.5`).
- `expression` must match what `explanation` describes — do not explain one operation while \
showing a different expression.
- The final step's `expression` must match the given final result exactly.

### Output Format
A list of steps, each with an `explanation` (spoken narration/subtitle text) and an `expression` \
(the mathematical expression at that point in the solution)."""


def solver_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Solve a math problem.

    Args:
        state: Current pipeline state (reads `user_input`).
        llm: LLM client to use for solving.

    Returns:
        Updated pipeline state with `solution` and `solvable` set.
    """

    # Step1: Generate sympy code for the computation needed to solve the problem
    extraction: Extraction = llm.generate_structured(
        prompt=f"Write a sympy code snippet from this problem: '{state['user_input']}'",
        schema=Extraction,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )

    # Step2: Execute the sympy code snippet to compute the solution
    namespace: dict[str, object] = {"sp": sp}
    try:
        exec(extraction.sympy_code, namespace)  # noqa: S102 — namespace limited to {"sp": sp}
        result = namespace.get("result")
        solvable = result is not None
    except Exception:  # noqa: BLE001 — exec() of LLM-generated code can raise any exception type
        result = None
        solvable = False

    # Step3: Convert the result into a step-by-step solution explanation
    if solvable:
        prompt = (
            f"Given the problem '{state['user_input']}' and the final result '{result}', "
            "write a step-by-step solution leading to this result."
        )
        solution = Solution(steps=[])
        for _ in range(MAX_EXPLANATION_ATTEMPTS):
            candidate: Solution = llm.generate_structured(
                prompt=prompt,
                schema=Solution,
                system_prompt=EXPLANATION_SYSTEM_PROMPT,
            )
            try:
                for step in candidate.steps:
                    sp.sympify(step.expression)
                solution = candidate
                break
            except Exception as e:  # noqa: BLE001 — sp.sympify() can raise any exception type on invalid syntax
                prompt = (
                    f"Given the problem '{state['user_input']}' and the final result '{result}', "
                    "write a step-by-step solution leading to this result.\n"
                    f"Your previous attempt included an expression sympy could not parse: {e}\n"
                    "Fix the syntax and write the full step-by-step solution again."
                )
        else:
            solvable = False
    else:
        solution = Solution(steps=[])

    state["solution"] = solution.steps
    state["solvable"] = solvable

    return state
