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
- Break the solution into many small steps. The viewer has to be able to follow every \
manipulation.
- Never jump straight to the result of a manipulation. Give it two steps: first the \
un-simplified form showing the operation being carried out, then the simplified result. Seeing \
the operation itself is what makes the video understandable, whatever the problem:
  - Equation — `Eq(x**2 - 4, 0)`, `Eq(x**2 - 4 + 4, 0 + 4)`, `Eq(x**2, 4)`.
  - Derivative — `Derivative(x**3 + 2*x, x)`, `Derivative(x**3, x) + Derivative(2*x, x)`, \
`3*x**2 + 2`.
  - Integral — `Integral(2*x + 1, x)`, `Integral(2*x, x) + Integral(1, x)`, `x**2 + x`.
  - Matrices, fractions, factorisation, substitution: the same — in-between form first, tidied \
form second.
- Write the un-simplified step exactly as it should appear on screen, leaving parts like \
`- 4 + 4`, `0 + 4` or an unevaluated `Derivative(...)` in place. Do not pre-simplify them.
- `explanation`: short, natural sentences for reading aloud, not textbook prose. It must match \
what its `expression` shows.
- `expression`: a plain sympy string parsed with `sp.sympify()`, so no `sp.` prefix — write \
`Derivative(x**2, x)`, not `sp.Derivative(x**2, x)`. Use `**` not `^`, `Eq(lhs, rhs)` not `==`, \
`Rational(1, 2)` not `1/2` (which becomes a float).
- The final step's `expression` must match the given final result exactly.

### Output Format
A list of steps, each with an `explanation` and an `expression`."""


def solver_node(state: PipelineState, llm: BaseLLM) -> PipelineState:
    """Solve a math problem.

    Args:
        state: Current pipeline state (reads `problem_statement`).
        llm: LLM client to use for solving.

    Returns:
        Updated pipeline state with `solution` and `solvable` set.
    """

    # Step1: Generate sympy code for the computation needed to solve the problem
    extraction: Extraction = llm.generate_structured(
        prompt=f"Write a sympy code snippet from this problem: '{state['problem_statement']}'",
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
            f"Given the problem '{state['problem_statement']}' and the final result '{result}', "
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
                    # Parsed the same way codegen_node will parse it, so a step
                    # that renders differently there cannot slip through here.
                    sp.sympify(step.expression, evaluate=False)
                solution = candidate
                break
            except Exception as e:  # noqa: BLE001 — sp.sympify() can raise any exception type on invalid syntax
                prompt = (
                    f"Given the problem '{state['problem_statement']}' and the final result '{result}', "
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
