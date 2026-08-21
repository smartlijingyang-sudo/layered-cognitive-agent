"""DefaultStopRule plugin — registers into STOP_RULES as 'default' (ADR-0074 PR-2)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import STOP_RULES
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer2_runtime.default_stop_rule import DefaultStopRule


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_default_stop_rule() -> DefaultStopRule:
    from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy

    return DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy())


# PR-2: typed control + functional_group + logic_address (stop.decide 槽位)
_DEFAULT_STOP_RULE_CONTROL: tuple[dict, ...] = (
    {
        "slot": ControlSlot.STOP_DECIDE.value,
        "order": 100,
        "aggregation": "stop_on_any_stop",
        "failure_mode": "stop",
        "effect_class": "none",
        "reads": ["state.steps", "state.wall_clock"],
        "emits": ["policy.stop.default.stopped"],
        "authority": ("stop_rules.read",),
    },
)


@plugin(
    id="stop_rule.default",
    provides=[],
    requires=[STOP_RULES.key],
    implements=[],
    layer="L1",
    effects="none",
    description="Register DefaultStopRule factory as stop_rules['default'].",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    control=_DEFAULT_STOP_RULE_CONTROL,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.STOP_DECIDE,
        scope=Scope.RUN,
        authority=("stop_rules.read",),
        evidence=("policy.stop.default.stopped",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STOP_RULES.key, "default", build_default_stop_rule)
