"""Fact scorer seam plugin (Tier-1).

声明 ``fact_scorers`` 注册中心；boot 后 ``providers/fact_scorer`` 把各种
``ScorerFn`` factory 注入。新增 fact scorer = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-fact-scorer-seam",
    provides=["fact_scorers"],
    layer="L0",
    effects="none",
    description="Provide the fact_scorers seam (facade plugin-ification).",
    test_suite="tests/test_fact_scorer_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("fact_scorers", NamedRegistry())
