# COMPAT(owner: ADR-0195 P4-S01, from: lca.plugins.session.runtime.repair,
# to: lca.session.repair,
# delete_when: rg 'plugins\.session\.runtime\.repair' lca/ tests/ = 0,
# forbidden_new_usage: true)
"""Deprecated shim — use :mod:`lca.session.repair`."""

from __future__ import annotations

from lca.session.repair import (
    TOOL_NOT_STARTED,
    TOOL_OUTCOME_UNKNOWN,
    SessionRepairError,
    repair_interrupted_turn,
)

__all__ = [
    "TOOL_NOT_STARTED",
    "TOOL_OUTCOME_UNKNOWN",
    "SessionRepairError",
    "repair_interrupted_turn",
]
