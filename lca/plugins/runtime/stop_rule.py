"""DefaultStopRule plugin — named factory ``stop_rule.default``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_default_stop_rule() -> DefaultStopRule:
    return DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy())


@plugin(name="stop_rule.default")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named StopRule factory ``stop_rule.default``."""
    ctx.provide("stop_rule.default", build_default_stop_rule)
