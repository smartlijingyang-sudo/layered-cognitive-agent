"""ProgressLoopDetector contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.progress-loop-detector",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Detect lack-of-progress loops and force a course change.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.TURN,
        authority=("decision.read", "loop.progress.read", "decision.rewrite"),
        evidence=("gate.progress-loop-detector.enforced",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.progress_loop_detector import (
        ProgressLoopDetector,
    )

    ctx.require("gates").add(
        ProgressLoopDetector, id="progress-loop-detector", slot="loop", order=30
    )
