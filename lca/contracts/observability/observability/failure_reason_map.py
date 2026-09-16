"""Closed-set ``failure_kind`` → ``error_reason`` map (PR-4, closes G-4).

Single source of truth for receipt failure classification. Add new entries
by extending :data:`FAILURE_KIND_TO_ERROR_REASON` here (closed-set by C11;
requires an ADR / new FAILURE_KIND_* constant). Nodes import from here;
no node-local map.
"""

from __future__ import annotations

from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TOOL_WIRE,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)

FAILURE_KIND_TO_ERROR_REASON: dict[str, str] = {
    FAILURE_KIND_EXECUTION: FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT: FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION: FAILURE_KIND_VALIDATION,
    FAILURE_KIND_TOOL_WIRE: FAILURE_KIND_TOOL_WIRE,
}


def resolve_error_reason(failure_kind: str | None) -> str | None:
    """Resolve ``failure_kind`` to its closed-set ``error_reason``.

    Unknown kinds and ``None`` both return ``None`` (no exception). The
    caller (``act.observe._normalize_receipt``) treats ``None`` as
    "leave ``error_code`` untouched".
    """
    return FAILURE_KIND_TO_ERROR_REASON.get(failure_kind) if failure_kind else None


__all__ = ["FAILURE_KIND_TO_ERROR_REASON", "resolve_error_reason"]
