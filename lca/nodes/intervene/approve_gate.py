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

import json
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
from lca.contracts.models.core.execution.external_content import (
    AuthorizationRefusal,
    ContentOrigin,
    refuse_external_authorization_claim,
    refuse_external_instruction_override,
)
from lca.contracts.observability.evidence.evidence import (
    Classification,
    RetentionClass,
)
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


def _external_content_refusal(decision: Decision) -> AuthorizationRefusal | None:
    """ADR-0292 C2: consult the two refusal doors for EXTERNAL-driven decisions.

    Returns the first tripped :class:`AuthorizationRefusal`, or ``None``
    when the decision carries no recorded external drive
    (``content_origin`` is not EXTERNAL), has no trigger text, or neither
    door trips. The seam detectors own the classification; this function
    only wires them to the typed ``Decision`` channel.
    """
    if decision.content_origin is not ContentOrigin.EXTERNAL:
        return None
    text = decision.origin_trigger_text
    if not text:
        return None
    refusals: list[AuthorizationRefusal] = []
    refuse_external_authorization_claim(text, on_refusal=refusals.append)
    refuse_external_instruction_override(text, on_refusal=refusals.append)
    return refusals[0] if refusals else None


def _route_refusal_to_evidence(refusal: AuthorizationRefusal, decision_id: str) -> None:
    """ADR-0292 C4 (wiring 4): route a blocked claim to the evidence ledger.

    Mechanical wiring per the 2026-10-05 section-9 adjudication: resolve the
    ambient evidence pair exactly like ``safe_executor._resolve_evidence_pair``
    and prepare the refusal payload (the blocked attack itself is the
    evidence). The import is deferred so this module never takes a hard
    dependency on the observability stack at load time. No bound
    observability (unit tests / offline paths) -> no-ref path: refusal
    routing still holds, only the evidence copy is skipped.
    """
    try:
        from lca.infrastructure.observability import current_bound
    except ImportError:  # pragma: no cover - packaged without observability
        return
    bound = current_bound()
    if bound is None:
        return
    store = bound.evidence_binding().store
    if store is None:
        return
    payload = json.dumps(
        {
            "event": "authorization_refusal",
            "gate": "act.approve.gate",
            "adr": "0292",
            "decision_id": decision_id,
            "kind": refusal.kind,
            "refused_at": refusal.refused_at.isoformat(),
            "text": refusal.text,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    store.prepare(
        payload,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
        media_type="application/json",
        prepared_by="act.approve.gate",
    )


@dataclass(frozen=True, slots=True)
class ApproveGateExecutor:
    """intervene node: gate ``decision`` flow on HITL approval semantics.

    The node is a pure transform of the typed ``decision`` + ``command``
    ports for routing purposes. It never reads ``context.runtime``, never
    mutates ``AgentState``. On the ``approve_refused`` path only, the gate
    additionally routes the refusal payload to the run-trace evidence
    ledger through the ambient observability seam (same pattern as
    ``safe_executor._resolve_evidence_pair``; no-ref path when unbound) —
    ADR-0292 C4, "the blocked attack itself is security evidence".
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
      to abort cleanly. ADR-0292 C2: also the routing for a refused
      EXTERNAL-driven privilege claim / instruction override — the claim
      never reaches ``act.envelope``; the refusal payload is routed to
      the run-trace evidence ledger (C4).
    """

    semantic_name: str = "act.approve.gate"
    region: str = "intervene"
    declared_inputs: tuple[PortName, ...] = (PortName("decision"), PortName("command"))
    # ADR-0237 / PR-1b: emit ``approval_routing`` (not ``routing``) so
    # the typed port does not collide with downstream ``act.fanout``'s
    # ``routing`` in the kernel-wide :class:`PortRegistry`
    # (last-write-wins would overwrite the gate's signal before the
    # outer plan reads it). The outer plan reads via
    # ``act.main.declared_outputs: [approval_routing]``.
    declared_outputs: tuple[PortName, ...] = (PortName("decision"), PortName("approval_routing"))

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.approve.gate 入口。

        inputs 端口(yaml): decision (Decision), command (Command, optional)
        outputs 端口(yaml): decision (Decision), approval_routing (RoutingDecision)

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

        # ADR-0292 C2 (wiring 1): security gate before approval routing.
        # An EXTERNAL-driven decision whose trigger text asserts held
        # authority or overrides prior instructions is refused outright —
        # external content can never be a source of authorization, and no
        # user interrupt is spent on an attack.
        refusal = _external_content_refusal(decision)
        if refusal is not None:
            _route_refusal_to_evidence(refusal, decision.decision_id)
            refused_routing = RoutingDecision(
                action_type=ActionType.RESPOND,
                next_node="terminal.commit",
                next_hint=_NEXT_HINT_APPROVE_REJECTED,
            )
            refused_ports = {
                PortName("decision"): decision,
                PortName("approval_routing"): refused_routing,
            }
            if req is not None:
                refused_ports[PortName("approval_requirement")] = req
            return NodeOutput(port_values=refused_ports)

        if req is not None and hasattr(req, "required"):
            needs_approval = bool(req.required)
        else:
            needs_approval = bool(decision.needs_approval)

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
