import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

SECRET_VARIABLES = ("GEMINI_API_KEY",)

EVALUATION_TIMEOUT_SECONDS = 60


class UntrustedEvaluationError(Exception):
    """The child process crashed, timed out or answered with something unreadable."""


@dataclass(frozen=True)
class Plot:
    """An expression plottable as y = f(x)."""

    latex: str
    python: str
    variable: str


@dataclass(frozen=True)
class Description:
    latex: list[str]
    plot: Plot | None


def environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name not in SECRET_VARIABLES}


# --- Parent side: each call starts one child process. ---


def evaluate_snippet(code: str) -> tuple[str | None, str | None]:
    """`(result, None)`, `(None, None)` if no `result` was set, or `(None, error)`."""
    answer = _call({"operation": "snippet", "code": code})
    return answer["result"], answer["error"]


def first_parse_error(expressions: list[str]) -> str | None:
    """The first error `sp.sympify(expression, evaluate=False)` raises, if any."""
    error: str | None = _call({"operation": "parse", "expressions": expressions})["error"]
    return error


def describe(expressions: list[str], plot: bool = True) -> Description:
    """LaTeX for each expression and, if `plot`, the first one plottable as y = f(x)."""
    answer = _call({"operation": "describe", "expressions": expressions, "plot": plot})
    found = answer["plot"]
    return Description(latex=answer["latex"], plot=Plot(**found) if found else None)


def _call(request: dict[str, Any]) -> dict[str, Any]:
    """Runs `request` in a fresh `python -I` child without the Gemini key.

    `exec()` and `sp.sympify()` (i.e. `eval()`) on LLM output must never run in
    the process holding the key. `-I` keeps the cwd off `sys.path`, so this
    module may import only the stdlib and sympy. Answers are plain JSON strings.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-I", __file__],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=EVALUATION_TIMEOUT_SECONDS,
            env=environment(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UntrustedEvaluationError(
            f"sympy took longer than {EVALUATION_TIMEOUT_SECONDS} seconds."
        ) from None

    # The answer is the last stdout line; a snippet's own prints come before it.
    lines = completed.stdout.strip().splitlines()
    try:
        answer = json.loads(lines[-1]) if lines else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        detail = completed.stderr.strip().splitlines()[-1:] or ["no output"]
        raise UntrustedEvaluationError(f"sympy stopped unexpectedly: {detail[0]}")
    return answer


# --- Child side: runs only inside the child process. ---


def to_latex(expression: str) -> str:
    """Render a sympy expression as LaTeX, exactly as written: unevaluated so
    manipulations stay visible, `order="none"` so terms keep their position.
    """
    import sympy as sp

    return str(sp.latex(sp.sympify(expression, evaluate=False), order="none"))


def plottable(expressions: list[str]) -> Plot | None:
    """First expression plottable as y = f(x), skipping what `pycode` can't print."""
    import sympy as sp

    for expression in expressions:
        parsed = sp.sympify(expression)
        if not isinstance(parsed, sp.Expr) or parsed.is_number:
            continue
        symbols = parsed.free_symbols
        if len(symbols) != 1:
            continue
        try:
            python = str(sp.pycode(parsed))
        except ValueError:
            continue
        return Plot(latex=str(sp.latex(parsed)), python=python, variable=symbols.pop().name)
    return None


def _run_snippet(code: str) -> dict[str, Any]:
    import sympy as sp

    namespace: dict[str, object] = {"sp": sp}
    try:
        exec(code, namespace)  # noqa: S102 — isolated child, see _call()
    except Exception as e:  # noqa: BLE001 — exec() of LLM-generated code can raise any exception type
        return {"result": None, "error": str(e)}
    result = namespace.get("result")
    return {"result": None if result is None else str(result), "error": None}


def _first_parse_error(expressions: list[str]) -> dict[str, Any]:
    import sympy as sp

    for expression in expressions:
        try:
            sp.sympify(expression, evaluate=False)
        except Exception as e:  # noqa: BLE001 — sp.sympify() can raise any exception type on invalid syntax
            return {"error": str(e)}
    return {"error": None}


def _describe(expressions: list[str], plot_wanted: bool) -> dict[str, Any]:
    plot = plottable(expressions) if plot_wanted else None
    return {
        "latex": [to_latex(expression) for expression in expressions],
        "plot": None if plot is None else plot.__dict__,
    }


def _serve() -> None:
    request = json.loads(sys.stdin.read())
    answer_to = sys.stdout
    sys.stdout = sys.stderr  # a snippet's prints must not interleave with the answer
    operation = request["operation"]
    if operation == "snippet":
        answer = _run_snippet(request["code"])
    elif operation == "parse":
        answer = _first_parse_error(request["expressions"])
    else:
        answer = _describe(request["expressions"], request["plot"])
    answer_to.write("\n" + json.dumps(answer) + "\n")
    answer_to.flush()


if __name__ == "__main__":
    _serve()
