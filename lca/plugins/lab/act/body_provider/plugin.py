# PR-D final — body provider (lazy composition)
"""lab.body provider — composition entry for SimpleBody + PipelineSafeExecutor
+ InternalTransport.

Replaces the PR-B marker. The actual composition is **lazy**: the
real composition happens at call time (not at import time) so the
cordis-dependent transitive imports only fire when a Body is actually
requested (i.e. when act.execute is invoked, not when the loader
walks plugin modules).

For the cordis-dependent bundle boot path, see the LCA-level
body_provider plugin (lca.plugins.composer.act.body_provider).
"""

from __future__ import annotations


def get_body(allowed_tools=None):
    """Build a SimpleBody instance with the lab tool registry.

    Args:
        allowed_tools: optional whitelist; defaults to all tools in the
            LabToolRegistry. The SimpleToolRegistry is built once per call.
    """
    from agent_lab.nodes.act.execute import body as act_body
    return act_body.build_body(allowed_tools=allowed_tools)


def plan_ref_default() -> str:
    """Default plan_ref for the lab act phase."""
    from lca.plugins.lab.session.provider.plugin import PLAN_REF
    return PLAN_REF


__all__ = ["get_body", "plan_ref_default"]

# Register loader marker for the capability closure.
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_LAB_HOOKS["lab.act.body_provider"] = {"id": "body_provider", "stage": "composition"}