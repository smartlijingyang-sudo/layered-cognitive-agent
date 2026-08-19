"""Skills Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-skills-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.skills import SkillsService
    ctx.provide("skills", SkillsService())
