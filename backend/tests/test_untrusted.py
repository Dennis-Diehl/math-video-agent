import subprocess
import sys
from pathlib import Path

import pytest

from graph import untrusted
from graph.untrusted import (
    Plot,
    UntrustedEvaluationError,
    describe,
    evaluate_snippet,
    first_parse_error,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_evaluate_snippet_returns_the_result_as_text():
    assert evaluate_snippet("result = sp.solve(sp.Eq(sp.Symbol('x')**2 - 4, 0))") == (
        "[-2, 2]",
        None,
    )


def test_evaluate_snippet_reports_a_missing_result():
    assert evaluate_snippet("x = 1") == (None, None)


def test_evaluate_snippet_reports_what_the_code_raised():
    result, error = evaluate_snippet("result = 1 / 0")

    assert result is None
    assert error == "division by zero"


def test_evaluate_snippet_ignores_what_the_code_prints():
    assert evaluate_snippet("print('noise'); print('{}'); result = 2") == ("2", None)


def test_evaluate_snippet_cannot_see_the_gemini_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")

    result, _ = evaluate_snippet("import os; result = os.environ.get('GEMINI_API_KEY', 'absent')")

    assert result == "absent"


def test_evaluate_snippet_cannot_reach_the_callers_memory():
    # Runs in another process: the caller's globals are simply not there.
    result, _ = evaluate_snippet("import sys; result = 'nodes.solver' in sys.modules")

    assert result == "False"


def test_evaluate_snippet_gives_up_on_code_that_never_finishes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(untrusted, "EVALUATION_TIMEOUT_SECONDS", 1)

    with pytest.raises(UntrustedEvaluationError, match="longer than 1 seconds"):
        evaluate_snippet("while True: pass")


def test_evaluate_snippet_reports_a_child_that_dies():
    with pytest.raises(UntrustedEvaluationError, match="stopped unexpectedly"):
        evaluate_snippet("import os; os._exit(3)")


def test_first_parse_error_accepts_valid_expressions():
    assert first_parse_error(["Eq(x**2, 4)", "Derivative(x**3, x)"]) is None


def test_first_parse_error_names_the_first_invalid_expression():
    error = first_parse_error(["Eq(x, 2)", "Eq(x, )"])

    assert error is not None


def test_describe_renders_latex_and_finds_a_plottable_expression():
    description = describe(["Eq(x + y, 4)", "x**2 - 4"])

    assert description.latex == ["x + y = 4", "x^{2} - 4"]
    assert description.plot == Plot(latex="x^{2} - 4", python="x**2 - 4", variable="x")


def test_describe_finds_no_plot_without_a_single_variable_function():
    assert describe(["Eq(x + y, 4)"]).plot is None


def test_describe_reports_an_unparsable_expression():
    with pytest.raises(UntrustedEvaluationError):
        describe(["Eq(x, )"])


def test_environment_drops_the_gemini_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")

    assert "GEMINI_API_KEY" not in untrusted.environment()


@pytest.mark.skipif(sys.platform != "linux", reason="prctl is Linux-only")
def test_protect_memory_makes_the_process_non_dumpable():
    # In a child, so the test process itself stays dumpable.
    script = (
        "import ctypes; from graph.run_job import protect_memory; protect_memory(); "
        "print(ctypes.CDLL(None).prctl(3, 0, 0, 0, 0))"  # PR_GET_DUMPABLE
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "0"


def test_describe_only_looks_for_a_plot_when_asked():
    assert describe(["x**2 - 4"], plot=False).plot is None


def test_describe_skips_expressions_sympy_cannot_print_as_python():
    description = describe(["Derivative(x**3 + 2*x**5, x)", "3*x**2 + 10*x**4"])

    assert description.plot == Plot(
        latex="10 x^{4} + 3 x^{2}", python="10*x**4 + 3*x**2", variable="x"
    )
