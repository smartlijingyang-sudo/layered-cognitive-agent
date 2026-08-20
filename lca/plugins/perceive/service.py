"""Perceive group Definition — owns ctx.perceive."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="perceive",
    provides=["perceive"],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Perceive group registry; sensor plugins add() onto it.",
    test_suite="tests/test_composer_sensor_wiring.py",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer1_cognitive.perceive_service import PerceiveService

    try:
        ctx.inject("perceive")
    except KeyError:
        ctx.provide("perceive", PerceiveService())
