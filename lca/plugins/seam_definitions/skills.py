"""Skills Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.operational_skills import SkillPackageInstaller
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-skills-service",
    provides=["skills"],
    implements=[SkillPackageInstaller],
    layer="L0",
    effects="none",
    description="Provide the Skills Definition service (ProviderDispatch + installer seam table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.capability.skills import SkillsService

    ctx.provide("skills", SkillsService())
