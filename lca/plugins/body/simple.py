"""SimpleBody plugin — registers into the BODIES registry seam."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.capabilities import BODIES
from lca.contracts.protocols import Body
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


_BODY_CONTROL: tuple[dict, ...] = (
    {
        "contribution_id": "body.simple.act-authorize",
        "slot": ControlSlot.ACT_AUTHORIZE.value,
        "order": 10,
        "aggregation": "deny_on_any_deny",
        "failure_mode": "deny",
        "effect_class": "tools",
        "reads": ["decision.action_type", "decision.tool_calls"],
        "emits": ["policy.act.authorize"],
        "authority": ("tools.authorize",),
    },
    {
        "contribution_id": "body.simple.act-budget",
        "slot": ControlSlot.ACT_BUDGET.value,
        "order": 20,
        "aggregation": "deny_on_exhausted",
        "failure_mode": "deny",
        "effect_class": "tools",
        "reads": ["state.budget"],
        "emits": ["policy.act.budget"],
        "authority": ("budget.read",),
    },
    {
        "contribution_id": "body.simple.act-constrain",
        "slot": ControlSlot.ACT_CONSTRAIN.value,
        "order": 30,
        "aggregation": "deny_on_any_deny",
        "failure_mode": "deny",
        "effect_class": "tools",
        "reads": ["decision.tool_calls"],
        "emits": ["policy.act.constrain"],
        "authority": ("tools.constrain",),
    },
    {
        "contribution_id": "body.simple.act-execute",
        "slot": ControlSlot.ACT_EXECUTE.value,
        "order": 40,
        "failure_mode": "stop",
        "effect_class": "tools",
        "reads": ["decision.action_type", "decision.delegations"],
        "emits": ["policy.act.execute"],
        "authority": ("tools.execute",),
    },
    {
        "contribution_id": "body.simple.act-safe-boundary",
        "slot": ControlSlot.ACT_SAFE_BOUNDARY.value,
        "order": 50,
        "failure_mode": "stop",
        "effect_class": "tools",
        "reads": ["state.status", "decision.action_type"],
        "emits": ["policy.act.safe-boundary"],
        "authority": ("tools.safe-boundary",),
    },
)


@plugin(
    id="body.simple",
    requires=[BODIES.key],
    implements=[Body],
    layer="L1",
    effects="tools",
    description="Register SimpleBody as bodies['simple'].",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    control=_BODY_CONTROL,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.layer1_cognitive.body.simple_body import SimpleBody

    ctx.register(BODIES.key, "simple", SimpleBody)
