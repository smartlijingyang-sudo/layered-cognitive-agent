"""Focused tests for the SafeExecutor retry policy through the barrel.

The retry policy is split into ``safe_executor.retry`` and re-exported by the
``safe_executor`` package. These tests pin the transient-vs-deterministic
classification and backoff math that ``SimpleSafeExecutor`` relies on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.cognition.body.executor.safe_executor import (
    classify_failure_kind,
    is_retryable_failure,
    next_backoff_delay,
)
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import RetryPolicy


@dataclass
class _Obs:
    success: bool = True
    payload: dict[str, Any] | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _failed_observation(failure_kind: str) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        extra={FAILURE_KIND: failure_kind},
    )


def test_classify_failure_kind_marks_deterministic_exceptions_as_execution() -> None:
    """Code bugs / bad input are deterministic — retrying is pointless."""
    for exc in (ValueError("bad input"), FileNotFoundError("missing"), PermissionError()):
        assert classify_failure_kind(exc) == FAILURE_KIND_EXECUTION


def test_classify_failure_kind_marks_transient_exceptions_as_transient() -> None:
    """Network timeouts / resource unavailability are transient and retryable."""
    for exc in (TimeoutError(), ConnectionError(), OSError("transient")):
        assert classify_failure_kind(exc) == FAILURE_KIND_TRANSIENT


def test_is_retryable_failure_true_for_transient_kind() -> None:
    assert is_retryable_failure(_failed_observation(FAILURE_KIND_TRANSIENT)) is True


def test_is_retryable_failure_false_for_execution_kind() -> None:
    assert is_retryable_failure(_failed_observation(FAILURE_KIND_EXECUTION)) is False


def test_is_retryable_failure_false_when_kind_missing() -> None:
    assert is_retryable_failure(_Obs(extra={})) is False


def test_next_backoff_delay_applies_multiplier() -> None:
    policy = RetryPolicy(backoff_base_s=0.5, backoff_multiplier=3.0)
    assert next_backoff_delay(0.5, policy) == 1.5
    assert next_backoff_delay(1.5, policy) == 4.5


def test_retry_policy_helpers_are_importable_through_barrel() -> None:
    """The package barrel keeps the retry policy importable from the old path."""
    import lca.cognition.body.executor.safe_executor as safe_mod

    assert safe_mod.classify_failure_kind is classify_failure_kind
    assert safe_mod.is_retryable_failure is is_retryable_failure
    assert safe_mod.next_backoff_delay is next_backoff_delay
