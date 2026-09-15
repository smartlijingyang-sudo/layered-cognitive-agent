"""region:intervene.act_approve_gate — typed-boundary HITL gate node.

Per ADR-0228 §Decision 4 + `2026-09-15-pr3.8-borrowed-nodes-design.md` §2.6:
``act.approve.gate`` is the act-side typed view of the HITL pause/resume
seam. It reads the ``decision`` produced upstream by ``act.authorize``
(``decision.extra["needs_approval"]`` flag), and on resume the kernel
re-projects the persisted ``Command`` as a typed ``command`` port.

Boundary discipline:

- AGENTS.md §3 C1 — no new phase, no new EP name. The node lives in the
  existing ``region:intervene`` sibling subgraph (ADR-0228 §3).
- AGENTS.md §3 C5 — capability monotonicity. The node reads
  ``decision.extra["needs_approval"]``; it does not grant capabilities,
  and the ``Command.resume`` flow handles capability re-check at
  ``act.envelope`` re-entry.
- AGENTS.md §3 C7 — control / observation split. ``Command`` is a
  control-plane artifact, but every emission lands in the journal as
  a ``SessionEvent`` first (observation); this node returns a typed
  ``RoutingDecision`` and lets the kernel persist, it does not mutate
  state directly.
- AGENTS.md §3 C10 — interrupt before envelope mint. The
  ``approve_interrupt`` branch routes to ``intervene.interrupt`` which
  pauses before any ``act.envelope`` mint.
- AGENTS.md §3 C13 — ``Command`` is the existing Pydantic-frozen
  ``extra="forbid"`` cross-graph DTO at
  ``lca.contracts.protocols.graph.command``; the gate reuses it for the
  resume payload.

Canonical node shape (ADR-0228 §Decision 2): hand-written
``@dataclass(frozen=True, slots=True)`` + ``@plugin(...)`` carrier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.core.execution.decision import Decision
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

_NEEDS_APPROVAL_KEY = "needs_approval"

# ``next_hint`` values consumed by the outer bundle edges in
# ``bundles/outer/phase_main.yaml``. They are control-plane metadata;
# the kernel uses ``next_node`` to route and ignores ``next_hint`` for
# routing decisions (per ``lca.contracts.protocols.graph.routing``).
_NEXT_HINT_APPROVE_SKIPPED = "approve_skipped"
_NEXT_HINT_APPROVE_INTERRUPT = "approve_interrupt"
_NEXT_HINT_APPROVE_APPROVED = "approve_approved"
_NEXT_HINT_APPROVE_REJECTED = "approve_rejected"


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``.

    Mirrors the seam used by ``intervene.interrupt`` / ``intervene.resume``
    so the typed-boundary contract is uniform across the intervene subgraph.
    """
    value = input.port_values.get(name)
    if value is None and getattr(context, "runtime", None) is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    return value


@dataclass(frozen=True, slots=True)
class ApproveGateExecutor:
    """intervene node: gate ``decision`` flow on HITL approval semantics.

    The node is a pure transform of the ``decision`` + ``command``
    ports. It never reads runtime state, never mutates ``AgentState``,
    and never touches I/O. The four routing outcomes:

    - ``approve_skipped`` — ``decision.extra.needs_approval`` is absent
      or False → pass-through to ``act.envelope`` with the original
      decision.
    - ``approve_interrupt`` — ``decision.extra.needs_approval`` is True
      and no ``command`` is present → route to ``intervene.interrupt``
      to collect the user's typed ``Command``.
    - ``approve_approved`` — ``command.kind == "approve"`` → resume to
      ``act.envelope`` with the original decision.
    - ``approve_rejected`` — ``command.kind`` is ``"reject"`` /
      ``"redirect"`` (redirect treated as abandon per spec §2.6) or
      ``command.kind == "resume"`` (timeout / abandon per the same
      clause) → route to ``terminal.commit`` to abort cleanly.
    """

    semantic_name: str = "act.approve.gate"
    region: str = "region:intervene"
    declared_inputs: tuple[PortName, ...] = ("decision", "command")
    declared_outputs: tuple[PortName, ...] = ("decision", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.approve.gate 入口。

        inputs 端口(yaml): decision (Decision), command (Command, optional)
        outputs 端口(yaml): decision (Decision), routing (RoutingDecision)
        """
        decision = _resolve_port("decision", input=input, context=context)
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.approve.gate: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        command = _resolve_port("command", input=input, context=context)
        if command is not None and not isinstance(command, Command):
            raise TypeError(
                "act.approve.gate: 'command' port must be a Command or None, "
                f"got {type(command).__name__}"
            )

        needs_approval = bool(decision.extra.get(_NEEDS_APPROVAL_KEY, False))

        if not needs_approval:
            next_hint = _NEXT_HINT_APPROVE_SKIPPED
            next_node = "act.envelope"
        elif command is None:
            next_hint = _NEXT_HINT_APPROVE_INTERRUPT
            next_node = "intervene.interrupt"
        elif command.kind == "approve":
            next_hint = _NEXT_HINT_APPROVE_APPROVED
            next_node = "act.envelope"
        else:
            # ``reject`` / ``redirect`` (treated as abandon) / ``resume``
            # (timeout / abandon signal): all four spec §2.6 abort paths
            # converge on terminal.commit; we never slip into
            # ``act.envelope`` for non-approve kinds.
            next_hint = _NEXT_HINT_APPROVE_REJECTED
            next_node = "terminal.commit"

        routing = RoutingDecision(
            action_type=ActionType.ASK_HUMAN
            if next_hint == _NEXT_HINT_APPROVE_INTERRUPT
            else ActionType.RESPOND,
            next_node=next_node,
            next_hint=next_hint,
        )
        return NodeOutput(port_values={"decision": decision, "routing": routing})


@plugin(
    id="lca.nodes.intervene.approve_gate",
    Config=None,
    provides=("region:intervene::act.approve.gate",),
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
                "phase_intervene_approve_gate.checked",
                "phase_intervene_approve_gate.served",
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
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ApproveGateExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ApproveGateExecutor", "setup"]
