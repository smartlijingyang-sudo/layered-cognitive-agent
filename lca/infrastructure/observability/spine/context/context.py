"""Spine context re-exports — ``SpanContext`` / ``SpineContext`` live in contracts.

The span-stack mechanism and records are pure-stdlib and belong to the
contract layer (:mod:`lca.contracts.observability.spine.context`). This
module keeps the historical import path working for infrastructure and
plugin consumers.
"""

from __future__ import annotations

from lca.contracts.observability.spine.context import (
    PhaseMachineViolation as PhaseMachineViolation,
    PhaseMachineViolationError as PhaseMachineViolationError,
    SpanContext as SpanContext,
    SpineContext as SpineContext,
)

__all__ = [
    "PhaseMachineViolation",
    "PhaseMachineViolationError",
    "SpanContext",
    "SpineContext",
]
