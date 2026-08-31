"""Profile-selectable evaluator for declarative phase-graph loop guards."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """The default evaluator has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-declarative-loop-guard",
    requires=[],
    provides=["loop_guard_evaluator"],
    implements=[LoopGuardEvaluator],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default declarative LoopGuard evaluator so profiles can replace "
        "loop re-entry policy without changing the graph interpreter."
    ),


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-declarative-loop-guard.checked', 'lca-declarative-loop-guard.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default pure loop-guard evaluator to runtime assembly."""

    del config
    ctx.provide("loop_guard_evaluator", DeclarativeLoopGuardEvaluator())


__all__ = ["Config", "setup"]
