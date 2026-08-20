"""ObservabilityScorer seam plugin (Tier-1) —— ADR-0063 PR-10.

声明 ``observability_scorer`` 服务形状；boot 后 ``providers/langfuse_eval`` 注册
Langfuse 评估打分回调。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-observability-scorer-seam",
    provides=["observability_scorer"],
    layer="L0",
    effects="network",
    description="Provide the observability_scorer seam (PR-10).",
    test_suite="tests/test_observability_scorer.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("observability_scorer", NamedRegistry())