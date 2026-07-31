"""Stop rule re-exports (compat module path).

Canonical definitions live in ``lca.contracts.stop``.
"""

from __future__ import annotations

from lca.contracts.stop import StopDecision, StopReason, StopRule

# Transitional aliases — remove after one release cycle.
LoopJudge = StopRule
TerminationReason = StopReason
TerminationSignal = StopDecision

__all__ = [
    "LoopJudge",
    "StopDecision",
    "StopReason",
    "StopRule",
    "TerminationReason",
    "TerminationSignal",
]
