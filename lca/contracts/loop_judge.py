"""Stop rule re-exports (compat module path).

Canonical definitions live in ``lca.contracts.stop``.
"""

from __future__ import annotations

from lca.contracts.stop import StopDecision, StopReason, StopRule

__all__ = [
    "StopDecision",
    "StopReason",
    "StopRule",
]
