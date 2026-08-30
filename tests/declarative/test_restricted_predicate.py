"""Safety and behavior coverage for declarative graph predicate evaluation."""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseResult,
)
from lca.harness.declarative.predicate import evaluate_restricted_predicate


def _result() -> PhaseResult:
    return PhaseResult(result_kind="decision", payload={"status": "ready", "count": 2})


def test_predicate_evaluates_only_declared_roots() -> None:
    assert evaluate_restricted_predicate(
        "result.payload.status == 'ready' and artifact['source'] == 'user'",
        result=_result(),
        artifacts={"payload": {"source": "user"}},
    )


def test_predicate_supports_membership_and_ordered_comparisons() -> None:
    assert evaluate_restricted_predicate(
        "result.payload.count >= 2 and 'done' in artifact",
        result=_result(),
        artifacts={"payload": ("queued", "done")},
    )


@pytest.mark.parametrize(
    "expression",
    (
        "unknown == 1",
        "result.__class__",
        "result.payload.get('status')",
        "[item for item in artifact]",
    ),
)
def test_predicate_rejects_undeclared_or_effectful_syntax(expression: str) -> None:
    with pytest.raises(DeclarativeValidationError, match="PS-001"):
        evaluate_restricted_predicate(
            expression,
            result=_result(),
            artifacts={"payload": {"source": "user"}},
        )


def test_predicate_reports_invalid_expressions_with_stable_code() -> None:
    with pytest.raises(DeclarativeValidationError, match="invalid restricted predicate"):
        evaluate_restricted_predicate(
            "result.payload.status = 'ready'",
            result=_result(),
            artifacts={},
        )
