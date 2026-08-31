"""GateChainComposer Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-gate-chain-composer-seam",
    provides=["gate_chain_composer"],
    requires=[],
    implements=["GateChainComposer"],
    layer="L1",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the GateChainComposer Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('decision.emit',),
        evidence=('lca-gate-chain-composer-seam.checked', 'lca-gate-chain-composer-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('decision.emit', 'gate_chain_composer'),
        emits=('gate_chain_composer.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.gate.gate_chain_composer import DefaultGateChainComposer

    ctx.provide("gate_chain_composer", DefaultGateChainComposer())


__all__ = ["setup"]
