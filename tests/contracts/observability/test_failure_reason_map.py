"""Closed-set ``failure_kind`` → ``error_reason`` map (PR-4, closes G-4).

Single source of truth for receipt failure classification lives in
``lca.contracts.observability.observability.failure_reason_map``. Nodes
import from here; no node-local map.

C11 closed-set: a new ``failure_kind`` is added by extending the dict
in the contracts module (after ADR), never in a node.
"""

from __future__ import annotations

from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TOOL_WIRE,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.observability.observability.failure_reason_map import (
    FAILURE_KIND_TO_ERROR_REASON,
    resolve_error_reason,
)


def test_failure_reason_map_contains_all_known_kinds() -> None:
    """All four known failure_kind values resolve via the closed-set map."""
    assert FAILURE_KIND_EXECUTION in FAILURE_KIND_TO_ERROR_REASON
    assert FAILURE_KIND_TRANSIENT in FAILURE_KIND_TO_ERROR_REASON
    assert FAILURE_KIND_VALIDATION in FAILURE_KIND_TO_ERROR_REASON
    assert FAILURE_KIND_TOOL_WIRE in FAILURE_KIND_TO_ERROR_REASON


def test_resolve_error_reason_known_kind_returns_value() -> None:
    """Known failure_kind resolves to its closed-set entry."""
    assert resolve_error_reason(FAILURE_KIND_EXECUTION) == FAILURE_KIND_EXECUTION
    assert resolve_error_reason(FAILURE_KIND_TRANSIENT) == FAILURE_KIND_TRANSIENT


def test_resolve_error_reason_unknown_returns_none() -> None:
    """Unknown failure_kind resolves to None (no exception)."""
    assert resolve_error_reason("unknown_kind_xyz") is None


def test_resolve_error_reason_none_returns_none() -> None:
    """None input returns None (no exception)."""
    assert resolve_error_reason(None) is None
