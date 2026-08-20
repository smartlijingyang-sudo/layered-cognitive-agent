"""Skills Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(
    name="lca-skills-provider",
    requires=["skills"],
    implements=[SkillPackageStore],
    layer="provider",
    side_effects="none",
    policy_class="control",
    description="Register SkillPackageStore providers on the SkillsService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.inject("skills").register("disk", resolve_skill_store())
