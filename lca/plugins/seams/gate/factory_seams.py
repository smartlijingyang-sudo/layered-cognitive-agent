"""Empty factory / strategy registry seams (ADR-0062 §3 / PR-3)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import (
    BODIES,
    BRAINS,
    HOOKS,
    RESUME_INPUT_ADAPTERS,
    STRATEGIES,
)
from lca.contracts.mechanisms.factory_registry import FactoryRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-factory-seams-default",
    provides=[
        BODIES.key,
        BRAINS.key,
        HOOKS.key,
        RESUME_INPUT_ADAPTERS.key,
        STRATEGIES.key,
    ],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=("Empty BODIES/BRAINS/HOOKS/RESUME_INPUT_ADAPTERS/STRATEGIES registry seams."),
    test_suite="tests/test_plugin_alignment.py::test_factory_registry_seams",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide(BODIES.key, FactoryRegistry("bodies"))
    ctx.provide(BRAINS.key, FactoryRegistry("brains"))
    ctx.provide(HOOKS.key, FactoryRegistry("hooks"))
    ctx.provide(
        RESUME_INPUT_ADAPTERS.key,
        FactoryRegistry("resume_input_adapters"),
    )
    ctx.provide(STRATEGIES.key, FactoryRegistry("team_strategies"))
