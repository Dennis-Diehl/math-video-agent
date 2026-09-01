"""solver_node — solve a math problem into steps a video can show, via sympy."""

import sympy as sp

from config.llm.base import BaseLLM
from config.schemas import Extraction, Solution
from graph.pipeline_state import PipelineState

MAX_EXPLANATION_ATTEMPTS = 3

# Appended to every failure message. The user cannot see what sympy choked on,
# only their own wording, so the advice has to be about the wording.
REPHRASE_HINT = (
    " Try stating the problem more explicitly — name the variable to solve for and "
    "write the operation out, for example 'differentiate x**3 + 2*x with respect to x'."
)

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
- Step 1 is the problem exactly as given, untouched. The viewer must see where you start from.
- After that, one step for every line a person would write down solving this on paper, whatever \
the topic. Each such line takes exactly two steps, never one and never three:
  1. the operation written out but not yet worked out;
  2. the result of working it out.
- What counts as a line worth writing down: applying a rule, applying a named formula \
(determinant, quadratic formula, a binomial identity), multiplying out brackets, factoring, \
isolating a term, substituting, cancelling. Each of these gets its two steps even when it looks \
like plain arithmetic.
- What does not: arithmetic a viewer does in their head. It is folded into the step it belongs \
to, and one such step may work out any amount of it at once. But it must stay traceable — the \
previous step has to show the numbers it came from.
- So `Derivative(x**3, x)`, `3*x**(3 - 1)`, `3*x**2` is right: the rule is visible before it is \
worked out. Jumping from `Derivative(x**3 + 2*x, x)` to `3*x**2 + 2` is wrong, and so is \
spending a step on `2*1` becoming `2`. If a step's `explanation` is only "now we calculate", it \
should not be a step.
- Write the not-yet-worked-out step exactly as it should appear on screen, leaving parts like \
`- 4 + 4`, `0 + 4`, `(2 - lamda)*(2 - lamda) - 1*1` or an unevaluated `Derivative(...)` in \
place. Do not pre-simplify them.
- Keep terms in the same order from one step to the next. `Derivative(x**2, x)*sin(x) + \
x**2*Derivative(sin(x), x)` becomes `2*x*sin(x) + x**2*cos(x)`, never the other way round: a \
term that jumps position looks to the viewer like it came from somewhere else.
- Matrix arithmetic is carried out the moment it is written, so `A - lamda*I` collapses to the \
subtracted matrix and the subtraction is never seen. Use `MatAdd` and `MatMul`, which stay as \
written — an eigenvalue problem therefore opens on the matrix, then \
`Eq(Determinant(MatAdd(Matrix([[2, 1], [1, 2]]), MatMul(-1, lamda, Matrix([[1, 0], [0, 1]])))), 0)`.
- A solution runs to about three to seven steps. Needing many more means arithmetic is being \
split up, or a standard result is being derived from scratch: solve a quadratic with the \
quadratic formula or by factoring, do not complete the square along the way.
- `explanation`: short, natural sentences for reading aloud, not textbook prose. It must match \
what its `expression` shows.
- `expression`: a plain sympy string parsed with `sp.sympify()`, so no `sp.` prefix — write \
`Derivative(x**2, x)`, not `sp.Derivative(x**2, x)`. Use `**` not `^`, `Eq(lhs, rhs)` not `==`, \
`Rational(1, 2)` not `1/2` (which becomes a float).
- A plain `/` already stays uncancelled, so write `(x - 3)*(x + 3)/(x - 3)` to show a fraction \
before it cancels. Never wrap anything in `UnevaluatedExpr`: it turns the denominator into a \
negative power and the fraction disappears.
- Name any symbol you introduce with a single letter or word — `P`, `n`, `area`. Underscores, \
brackets and spaces in a name are read as LaTeX markup and come out garbled.
- The final step's `expression` must match the given final result exactly.

### Output Format
A list of steps, each with an `explanation` and an `expression`."""


def solver_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Solve a math problem, setting `solution`/`solvable`/`error`."""
    extraction: Extraction = llm.generate_structured(
        prompt=f"Write a sympy code snippet from this problem: '{state['problem_statement']}'",
        schema=Extraction,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )

    namespace: dict[str, object] = {"sp": sp}
    error: str | None = None
    try:
        exec(extraction.sympy_code, namespace)  # noqa: S102 — namespace limited to {"sp": sp}
        result = namespace.get("result")
        solvable = result is not None
        if not solvable:
            error = "sympy produced no result for this problem." + REPHRASE_HINT
    except Exception as e:  # noqa: BLE001 — exec() of LLM-generated code can raise any exception type
        result = None
        solvable = False
        error = f"sympy could not evaluate this problem: {e}" + REPHRASE_HINT

    if solvable:
        prompt = (
            f"Given the problem '{state['problem_statement']}' and the final result '{result}', "
            "write a step-by-step solution leading to this result."
        )
        solution = Solution(steps=[])
        unparsed = ""
        for _ in range(MAX_EXPLANATION_ATTEMPTS):
            candidate: Solution = llm.generate_structured(
                prompt=prompt,
                schema=Solution,
                system_prompt=EXPLANATION_SYSTEM_PROMPT,
            )
            try:
                for step in candidate.steps:
                    sp.sympify(step.expression, evaluate=False)  # same parse codegen_node uses
                solution = candidate
                break
            except Exception as e:  # noqa: BLE001 — sp.sympify() can raise any exception type on invalid syntax
                unparsed = str(e)
                prompt = (
                    f"Given the problem '{state['problem_statement']}' and the final result '{result}', "
                    "write a step-by-step solution leading to this result.\n"
                    f"Your previous attempt included an expression sympy could not parse: {e}\n"
                    "Fix the syntax and write the full step-by-step solution again."
                )
        else:
            solvable = False
            error = f"The solution steps could not be parsed: {unparsed}" + REPHRASE_HINT
    else:
        solution = Solution(steps=[])

    state["solution"] = solution.steps
    state["solvable"] = solvable
    state["error"] = error

    return state
