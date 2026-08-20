"""Skills Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-skills-service")
async def setup(ctx: Context, config: Any) -> None:
    from lca.layer0_infra.capability.skills import SkillsService

    ctx.provide("skills", SkillsService())
