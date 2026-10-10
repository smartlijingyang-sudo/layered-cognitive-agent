"""region:intervene.act_approve_gate — typed-boundary HITL gate node.

Per ADR-0228: ``act.approve.gate`` is the act-side typed view of the
HITL pause/resume seam. It reads the typed ``decision`` produced
upstream by ``act.authorize`` (``decision.needs_approval`` typed field).
On resume the driver restarts from ``perceive.main`` with the human
answer folded into state (no ``command`` port re-entry).

Boundary discipline:

- AGENTS.md C4: Reducer single-write. The node only emits typed ports.
- AGENTS.md C10: interrupt before envelope mint. The ``approve_interrupt``
  branch routes to ``intervene.interrupt`` which pauses before any
  ``act.envelope`` mint.
- AGENTS.md C13: ``Command`` is the Pydantic-frozen cross-graph DTO.
  ``Decision.needs_approval`` is the typed Contract for the HITL signal.
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

# ``next_hint`` values consumed by the outer bundle edges in
# ``bundles/outer/phase_main.yaml``. They are control-plane metadata;
# the kernel uses ``next_node`` to route and ignores ``next_hint`` for
# routing decisions (per ``lca.contracts.protocols.graph.routing``).
_NEXT_HINT_APPROVE_SKIPPED = "approve_skipped"
_NEXT_HINT_APPROVE_INTERRUPT = "approve_interrupt"
_NEXT_HINT_APPROVE_APPROVED = "approve_approved"
_NEXT_HINT_APPROVE_REJECTED = "approve_rejected"


@dataclass(frozen=True, slots=True)
class ApproveGateExecutor:
    """intervene node: gate ``decision`` flow on HITL approval semantics.

    The node reads the typed ``decision`` / ``command`` /
    ``approval_requirement`` ports and routes on HITL semantics. 能力授权
    检查不在本节点：ADR-0292 §10 P3 的运行时授权检查前移到 ``act.authorize``
    （``grant_routing`` 端口），本节点只负责审批暂停/恢复路由。
    It never reads ``context.runtime`` and never mutates ``AgentState``.
    The four routing outcomes:

    - ``approve_skipped`` — ``decision.needs_approval`` is False →
      pass-through to ``act.envelope`` with the original decision.
    - ``approve_interrupt`` — ``decision.needs_approval`` is True and no
      ``command`` is present → route to ``intervene.interrupt`` to
      collect the user's typed ``Command``.
    - ``approve_approved`` — reserved for future surgical resume.
      Currently unreachable (full-restart resume enters at perceive.main).
    - ``approve_rejected`` — ``command.kind`` is ``"reject"`` /
      ``"redirect"`` or ``"resume"`` → route to ``terminal.commit``
      to abort cleanly.
    """

    semantic_name: str = "act.approve.gate"
    region: str = "intervene"
    # ADR-0292 §10: ``approval_requirement`` is the authoritative policy
    # signal minted by ``act.authorize``. Declaring it is load-bearing,
    # not decoration: the kernel projects ``NodeInput`` from
    # ``schema.required_inputs()``, so an undeclared port never reaches
    # the executor in a real graph run (unit tests that hand-build
    # ``NodeInput`` mask this).
    declared_inputs: tuple[PortName, ...] = (
        PortName("decision"),
        PortName("command"),
        PortName("approval_requirement"),
    )
    # ADR-0237 / PR-1b: emit ``approval_routing`` (not ``routing``) so
    # the typed port does not collide with downstream ``act.fanout``'s
    # ``routing`` in the kernel-wide :class:`PortRegistry`
    # (last-write-wins would overwrite the gate's signal before the
    # outer plan reads it). The outer plan reads via
    # ``act.main.declared_outputs: [approval_routing]``.
    declared_outputs: tuple[PortName, ...] = (
        PortName("decision"),
        PortName("approval_routing"),
        # Echoed through so the policy signal the gate acted on stays
        # visible in the port registry for outer consumers.
        PortName("approval_requirement"),
    )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.approve.gate 入口。

        inputs 端口(yaml): decision (Decision),
            approval_requirement (ApprovalRequirement),
            command (Command, optional)
        outputs 端口(yaml): decision (Decision),
            approval_routing (RoutingDecision),
            approval_requirement (ApprovalRequirement, echo)

        ADR-0235 / PR-5: reads typed ports only. No more
        ``_resolve_port(context, name)`` that peeked at
        ``context.runtime``. ``needs_approval`` is read from the typed
        ``Decision.needs_approval`` field (L-2 / G-9 follow-through).
        """
        decision = input.port_values.get(PortName("decision"))
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.approve.gate: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        command = input.port_values.get(PortName("command"))
        if command is not None and not isinstance(command, Command):
            raise TypeError(
                "act.approve.gate: 'command' port must be a Command or None, "
                f"got {type(command).__name__}"
            )

        req = input.port_values.get(PortName("approval_requirement"))

        # The policy signal is authoritative when present; without it the
        # gate falls back to the model's self-reported
        # ``decision.needs_approval``. The port is declared required so the
        # bundle wiring check fails loud at boot instead of degrading here.
        needs_approval = req.required if req is not None else decision.needs_approval

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
        port_values = {PortName("decision"): decision, PortName("approval_routing"): routing}
        if req is not None:
            port_values[PortName("approval_requirement")] = req
        return NodeOutput(port_values=port_values)


@plugin(
    id="lca.nodes.intervene.approve_gate",
    Config=None,
    provides=("intervene::act.approve.gate",),
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
