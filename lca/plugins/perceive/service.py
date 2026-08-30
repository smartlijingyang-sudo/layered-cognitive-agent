"""Perceive group Definition — owns ctx.perceive (ADR-0056 / ADR-0061)."""

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
    id="perceive",
    provides=["perceive"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Perceive group registry; sensor plugins add() onto it.",
    test_suite="tests/test_composer_sensor_wiring.py",
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.PROFILE,
        authority=("perceive.contribute",),
        evidence=("perceive.group.assembled",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.perceive_service import PerceiveService

    ctx.provide("perceive", PerceiveService())
