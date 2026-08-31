"""Empty factory / strategy registry seams (ADR-0062 §3 / PR-3)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    BODIES,
    BRAINS,
    HOOKS,
    RESUME_INPUT_ADAPTERS,
    STRATEGIES,
)
from lca.contracts.mechanisms.factory_registry import FactoryRegistry
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-factory-seams-default.checked", "lca-factory-seams-default.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
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
