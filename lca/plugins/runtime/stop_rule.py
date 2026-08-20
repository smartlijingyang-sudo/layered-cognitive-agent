"""DefaultStopRule plugin — registers into STOP_RULES as 'default'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import STOP_RULES
from lca.harness.plugin_api import PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_default_stop_rule():
    from lca.layer2_runtime.default_stop_rule import DefaultStopRule
    from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy

    return DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy())


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
)
async def setup(ctx, config: Config) -> None:
    del config
    ctx.register(STOP_RULES.key, "default", build_default_stop_rule)
