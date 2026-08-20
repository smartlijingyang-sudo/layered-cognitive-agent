"""Gate group Definition — owns ctx.gates (ADR-0056 / ADR-0061)."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import PluginKind, plugin


@plugin(
    id="gates",
    provides=["gates"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Gate group registry; gate plugins add() onto it.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer1_cognitive.gate_service import GateService

    ctx.provide("gates", GateService())
