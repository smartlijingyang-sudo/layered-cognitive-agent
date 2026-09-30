"""Retry policy for SafeExecutor — transient-vs-deterministic classification and backoff.

The executor retries only transient failures (network timeouts, resource
unavailability). Deterministic failures (``_DETERMINISTIC_EXCEPTIONS``, code
bugs, bad input) fail fast so the agent's ReAct loop can correct via critic
feedback instead of pointlessly re-invoking the same tool with the same args.
"""

from __future__ import annotations

from lca.cognition.body.internal._retry_classification import (
    _DETERMINISTIC_EXCEPTIONS,
)
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import RetryPolicy


def classify_failure_kind(exc: Exception) -> str:
    """Classify an unexpected tool exception as deterministic or transient.

    Deterministic errors (code bugs, bad input) will never succeed on retry —
    fail fast so the agent's ReAct loop can correct.
    """
    return (
        FAILURE_KIND_EXECUTION
        if isinstance(exc, _DETERMINISTIC_EXCEPTIONS)
        else FAILURE_KIND_TRANSIENT
    )


def is_retryable_failure(observation: Observation) -> bool:
    """True when a failed observation is a transient infrastructure error.

    Execution errors and validation rejections are deterministic — retrying
    with the same args is pointless.
    """
    return observation.extra.get(FAILURE_KIND) == FAILURE_KIND_TRANSIENT


def next_backoff_delay(delay: float, retry_policy: RetryPolicy) -> float:
    """Return the backoff delay for the following retry attempt."""
    return delay * retry_policy.backoff_multiplier
