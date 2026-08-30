"""Gate group Definition — owns ctx.gates (ADR-0056 / ADR-0061)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gates",
    provides=["gates"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Gate group registry; gate plugins add() onto it.",
    test_suite="tests/test_plugin_alignment.py",
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.PROFILE,
        authority=("gates.contribute",),
        evidence=("gates.group.assembled",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.gate_service import GateService

    ctx.provide("gates", GateService())
