"""Skills Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-skills-service",
    provides=["skills"],
    implements=[SkillPackageStore],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Provide the Skills Definition service (ProviderDispatch + skill store table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.skills import SkillsService

    ctx.provide("skills", SkillsService())
