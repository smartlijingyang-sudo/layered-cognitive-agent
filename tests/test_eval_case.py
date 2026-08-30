from __future__ import annotations

import pytest

from lca.contracts.harness.eval_case import EvalCase


def test_eval_case_matches_expected_terminal_result() -> None:
    case = EvalCase("case-1", "build report", "completed", ("report.md",))

    assert case.matches(status="completed", artifacts=("report.md", "chart.png")) is True
    assert case.matches(status="failed", artifacts=("report.md",)) is False


def test_eval_case_requires_stable_identity() -> None:
    with pytest.raises(ValueError):
        EvalCase("", "build report", "completed")
