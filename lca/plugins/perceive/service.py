"""Perceive group Definition — owns ctx.perceive (ADR-0056 / ADR-0061)."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import PluginKind, plugin


@plugin(
    id="perceive",
    provides=["perceive"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Perceive group registry; sensor plugins add() onto it.",
    test_suite="tests/test_composer_sensor_wiring.py",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer1_cognitive.perceive_service import PerceiveService

    ctx.provide("perceive", PerceiveService())
