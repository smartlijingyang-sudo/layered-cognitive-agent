"""Skills Provider plugin — Tier-2."""

from __future__ import annotations
from pydantic import BaseModel, Field
from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(
    id="lca-skills-provider",
    requires=["skills"],
    implements=[SkillPackageStore],
    layer="L0",
    effects="none",
    description="Register SkillPackageStore providers on the SkillsService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.inject("skills").register("disk", resolve_skill_store())
