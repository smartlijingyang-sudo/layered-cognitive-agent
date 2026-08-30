from __future__ import annotations

from lca.contracts.harness.eval_comparison import EvalComparison


def test_eval_comparison_passes_matching_result() -> None:
    comparison = EvalComparison("completed", "completed")

    assert comparison.passed is True
    assert comparison.summary() == "passed"


def test_eval_comparison_detects_regression() -> None:
    comparison = EvalComparison("completed", "partial", ("report.md",))

    assert comparison.passed is False
    assert comparison.summary() == "regression detected"
