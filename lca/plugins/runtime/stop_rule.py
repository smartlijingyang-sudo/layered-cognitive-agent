"""DefaultStopRule plugin — named factory ``stop_rule.default``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import StopRule
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_default_stop_rule() -> StopRule:
    from lca.layer2_runtime.default_stop_rule import DefaultStopRule
    from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy

    return DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy())


@plugin(
    id="stop_rule.default",
    provides=["stop_rule.default"],
    requires=[],
    implements=[],
    layer="L1",
    effects="none",
    description="Default StopRule factory used by the Composer when none is injected.",
    test_suite="tests/test_plugin_alignment.py::test_stop_rule_named_factory",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide the named StopRule factory ``stop_rule.default``."""
    ctx.provide("stop_rule.default", build_default_stop_rule)
