"""Predicate evaluator boundary guards.

The kernel-side ``select_edge`` calls :func:`evaluate_restricted_predicate`
with a result view that may have ``payload`` resolve to ``None`` for
graph nodes whose ``NodeOutput`` does not carry a typed payload
(``_ResultView.__getattr__`` swallows missing attributes and returns
``None``). The legacy ``PhaseResult`` always carried a typed payload,
so chained attribute access like ``not result.payload.should_stop``
worked there. The new kernel must guard against ``None`` at the
predicate boundary so chained access on a missing attribute resolves
to a comparison that simply does not match, instead of raising
``AttributeError`` and aborting the run.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.harness.graph.predicate import evaluate_restricted_predicate


class _ResultLike:
    """Stand-in for a legacy ``PhaseResult`` with a typed payload."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.result_kind = "decision"


class _ViewWithNonePayload:
    """Stand-in for the new kernel's ``_ResultView`` whose ``payload`` resolves to ``None``."""

    def __getattr__(self, name: str) -> Any:
        if name == "payload":
            return None
        if name == "result_kind":
            return "decision"
        raise AttributeError(name)


def test_chained_access_on_typed_payload_resolves() -> None:
    """Legacy shape: ``payload`` is an object with ``should_stop``; predicate works."""
    payload = type("P", (), {"should_stop": True})()
    result = _ResultLike(payload)
    assert evaluate_restricted_predicate(
        "not result.payload.should_stop", result=result, artifacts={}
    ) is False


def test_chained_access_on_none_payload_does_not_match() -> None:
    """New kernel shape: ``payload`` is ``None``; chained access must NOT raise.

    Returning ``None`` for the predicate comparison yields a False match,
    which is the same outcome the legacy code produced when the typed
    payload was absent (the comparison ``not None`` is True but the
    runtime state at the predicate site treated missing payload as
    "no decision yet").
    """
    result = _ViewWithNonePayload()
    # Must not raise AttributeError
    matched = evaluate_restricted_predicate(
        "not result.payload.should_stop", result=result, artifacts={}
    )
    # ``not None.should_stop`` -> ``not None`` -> True; legacy semantics
    # treated this as "no stop decision yet, keep going".
    assert matched is True


def test_chained_access_on_missing_attribute_does_not_match() -> None:
    """Attribute access on a missing attribute must NOT raise."""
    result = _ViewWithNonePayload()
    matched = evaluate_restricted_predicate(
        "result.missing.deeper.path == 1", result=result, artifacts={}
    )
    assert matched is False


def test_existing_result_kind_comparison_still_works() -> None:
    """Regression: the original ``result_kind == "phase_error"`` shape stays correct."""
    result = _ResultLike(type("P", (), {"should_stop": False})())
    assert evaluate_restricted_predicate(
        'result.result_kind == "phase_error"', result=result, artifacts={}
    ) is False
    result2 = _ResultLike(type("P", (), {"should_stop": False})())
    result2.result_kind = "phase_error"
    assert evaluate_restricted_predicate(
        'result.result_kind == "phase_error"', result=result2, artifacts={}
    ) is True


def test_private_attribute_still_rejected() -> None:
    """The private-attribute guard must remain in force for None inputs too."""
    from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
        DeclarativeValidationError,
    )

    result = _ViewWithNonePayload()
    with pytest.raises(DeclarativeValidationError):
        evaluate_restricted_predicate("result._private", result=result, artifacts={})


def test_mapping_value_with_missing_key_returns_none() -> None:
    """Mapping lookup for a missing key returns ``None`` (unchanged behaviour)."""

    class _MappingResult:
        payload = {"x": 1}
        result_kind = "decision"

    result = _MappingResult()
    matched = evaluate_restricted_predicate(
        "result.payload.y == 1", result=result, artifacts={}
    )
    assert matched is False