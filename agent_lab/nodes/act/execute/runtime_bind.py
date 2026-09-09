"""Process boot for act: just the plan_ref constant.

PR-C — replaces the global ``_PUBLISH_TOKEN`` / ``ensure_act_runtime``
machinery with a stub. The real Session binding now lives in
``lca.plugins.lab.session.provider`` (added in PR-D as a full @plugin
carrier that performs ``set_publish_session`` at setup).

The ``plan_ref()`` constant is retained here for backwards compatibility
with any caller that still imports it from this path. New callers should
import it from ``lca.plugins.lab.session.provider`` instead.
"""

from __future__ import annotations

_PLAN_REF = "agent_lab_act"


def plan_ref() -> str:
    """Return the lab act plan_ref constant (kept for backwards compat)."""
    return _PLAN_REF


__all__ = ["plan_ref"]