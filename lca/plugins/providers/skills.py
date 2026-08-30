"""Skills Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.operational_skills import SkillPackageInstaller
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(
    id="lca-skills-provider",
    requires=["skills"],
    implements=[SkillPackageInstaller],
    layer="L0",
    effects="none",
    description="Register SkillPackageInstaller providers on the SkillsService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.require("skills").register("disk", resolve_skill_store())
