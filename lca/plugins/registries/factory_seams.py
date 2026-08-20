"""Empty factory / strategy registry seams (ADR-0062 §3 / PR-3)."""

from __future__ import annotations

from typing import Any

from lca.contracts.capabilities import BODIES, BRAINS, HOOKS, STOP_RULES, STRATEGIES
from lca.contracts.mechanisms.factory_registry import FactoryRegistry
from lca.harness.plugin_api import PluginKind, plugin


@plugin(
    id="lca.registries.factory_seams",
    provides=[
        BODIES.key,
        BRAINS.key,
        STOP_RULES.key,
        HOOKS.key,
        STRATEGIES.key,
    ],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Empty BODIES/BRAINS/STOP_RULES/HOOKS/STRATEGIES registry seams.",
    test_suite="tests/test_plugin_alignment.py::test_factory_registry_seams",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    ctx.provide(BODIES.key, FactoryRegistry("bodies"))
    ctx.provide(BRAINS.key, FactoryRegistry("brains"))
    ctx.provide(STOP_RULES.key, FactoryRegistry("stop_rules"))
    ctx.provide(HOOKS.key, FactoryRegistry("hooks"))
    ctx.provide(STRATEGIES.key, FactoryRegistry("team_strategies"))
