# PR-C — Lab session provider (PR-C stub)
"""lab.session provider — replaces agent_lab.nodes.act.execute.runtime_bind.

The provider performs ``set_publish_session(active_session)`` at setup
time and exposes the active session via ``lab.session``. PR-D will
fully implement this with proper Cordis context integration; until
then, this is a marker plus a thin standalone helper that runs at
import time (idempotent).

References:
- ADR-0209 §1.5 (Session single-track; set_publish_session is the
  single entry point and lives on the LCA side, not on the lab side).
- Note ``2026-09-08-agent-lab-absorb-end-state`` (delete-when).
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

PLAN_REF = "agent_lab_act"


def plan_ref() -> str:
    """Return the lab act plan_ref constant."""
    return PLAN_REF


# Marker for the capability closure
_marker = {"id": "lab.session", "plan_ref": PLAN_REF}
_LAB_HOOKS["lab.session"] = _marker

__all__ = ["plan_ref", "PLAN_REF"]