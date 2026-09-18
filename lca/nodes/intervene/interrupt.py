"""region:intervene.interrupt — typed HITL pause primitive.

Per ADR-0228 §Decision 4: reads the upstream ``decision`` and
``spine_seq`` ports, emits a typed ``Command(kind="approve"|"reject")``
plus a ``RoutingDecision(should_terminate=True, next_hint="intervene.resume")``.
The kernel sees ``should_terminate`` and pauses. The driver
(``driver.py``) detects the pause signal and restarts the graph from
``perceive.main`` with the human answer folded into state.

Boundary discipline:

- AGENTS.md §3 C4 — Reducer single-write: this node only emits typed
  ports; it never mutates ``AgentState``.
- AGENTS.md §3 C13 — ``Command`` is the Pydantic-frozen
  ``extra="forbid"`` cross-graph DTO at
  ``lca.contracts.protocols.graph.command``.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision, requires_human_input
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.context.context import SpineContext

_HITL_ACTION_TYPE = "ask_user"
_DEFAULT_ISSUED_BY = "user"


@dataclass(frozen=True, slots=True)
class InterruptExecutor:
    """intervene node: project a HITL ``Decision`` into a typed ``Command``.

    Pure transform of typed ``decision`` + ``spine_seq`` ports. Never
    reads runtime state, never mutates ``AgentState``, never touches I/O.
    """

    semantic_name: str = "intervene.interrupt"
    region: str = "intervene"
    declared_inputs: tuple[PortName, ...] = ("decision", "spine_seq")
    declared_outputs: tuple[PortName, ...] = ("command", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            raise TypeError(
                f"intervene.interrupt expects Decision on port 'decision', "
                f"got {type(decision).__name__}"
            )
        seq = input.port_values.get("spine_seq")
        if seq is None:
            seq = SpineContext.current_sequence()
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise TypeError(
                f"intervene.interrupt expects int on port 'spine_seq', "
                f"got {type(seq).__name__}"
            )
        if decision.action_type == _HITL_ACTION_TYPE or requires_human_input(
            decision.tool_calls
        ):
            kind = "approve"
        else:
            kind = "reject"
        cmd = Command(
            kind=kind,  # type: ignore[arg-type]
            payload={"decision_id": decision.decision_id},
            issued_by=_DEFAULT_ISSUED_BY,
            issued_at_seq=seq,
        )
        routing = RoutingDecision(
            action_type=ActionType.ASK_HUMAN,
            should_terminate=True,
            next_hint="intervene.resume",
        )
        return NodeOutput(port_values={"command": cmd, "routing": routing})


@plugin(
    id="lca.nodes.intervene.interrupt",
    Config=None,
    provides=("intervene::intervene.interrupt",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_intervene_interrupt.checked",
                "phase_intervene_interrupt.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    del config
    executor = InterruptExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["InterruptExecutor", "setup"]
