"""Gate group Definition — owns ctx.gates."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="gates",
    provides=["gates"],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Gate group registry; gate plugins add() onto it.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer1_cognitive.gate_service import GateService

    try:
        ctx.inject("gates")
    except KeyError:
        ctx.provide("gates", GateService())
