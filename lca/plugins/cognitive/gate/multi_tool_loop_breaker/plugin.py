"""MultiToolLoopBreakerGate contribution — posts onto GateService (ADR-0214 PR-B).

Complement to ``gate.tool-loop-breaker``.  Runs *after* the single-tool
breaker (order=25) so single-tool patterns break first; multi-tool
breaker handles the wider view (tool switches, fingerprint flatlines,
confidence erosion).

Wires the ``TaskProgressProjection`` into ``state.task_progress_projection``
on every TURN boundary so the gate can read it without depending on
plugin ordering side effects.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.multi-tool-loop-breaker",
    requires=["gates", "loop_guard_policy"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Wide-angle progress breaker: stuck / flatlined / static-fingerprint.",
    test_suite="tests/cognition/test_multi_tool_loop_breaker.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.THINK_GUARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(
            grants=("decision.read", "loop.progress.read", "decision.rewrite"),
        ),
        observability=EvidenceContract(
            descriptors=("gate.multi-tool-loop-breaker.enforced",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        MultiToolLoopBreakerGate,
    )
    from lca.plugins.cognitive.gate._loop_policy import resolve_loop_thresholds

    thresholds = resolve_loop_thresholds(ctx)
    ctx.require("gates").add(
        lambda: MultiToolLoopBreakerGate(thresholds=thresholds),
        id="multi-tool-loop-breaker",
        slot="loop",
        order=25,
    )
