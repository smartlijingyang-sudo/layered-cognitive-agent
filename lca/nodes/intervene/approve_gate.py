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
from datetime import UTC, datetime

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
from lca.contracts.models.core.execution.approval import ApprovalRequirement
from lca.contracts.models.core.execution.decision import Decision
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
from lca.contracts.runtime.trust import get_current_trust_envelope
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ``next_hint`` values consumed by the outer bundle edges in
# ``bundles/outer/phase_main.yaml``. They are control-plane metadata;
# the kernel uses ``next_node`` to route and ignores ``next_hint`` for
# routing decisions (per ``lca.contracts.protocols.graph.routing``).
_NEXT_HINT_APPROVE_SKIPPED = "approve_skipped"
_NEXT_HINT_APPROVE_INTERRUPT = "approve_interrupt"
_NEXT_HINT_APPROVE_APPROVED = "approve_approved"
_NEXT_HINT_APPROVE_REJECTED = "approve_rejected"


def _grant_absence_refusal(
    decision: Decision, req: ApprovalRequirement | None
) -> tuple[list[str], bool] | None:
    """ADR-0292 section 10: fail-closed grant check for privileged actions.

    A decision is *privileged* when the ``approval_requirement`` port's
    ``required`` flag is set — the authoritative policy signal from
    ``act.authorize`` (``ApprovalPolicyEngine``), not the model's
    self-reported ``decision.needs_approval`` (which a hallucinating model
    can clear while claiming authorization; §10's grant check is precisely
    the backstop for that case).

    For privileged decisions, every tool call names its required privilege
    in ``capability.verb`` form (e.g. ``"shell.exec"``); the ambient
    TrustEnvelope (ADR-0199, bound via ``trust_envelope_scope``) must grant
    each one. A missing grant — including the case where no envelope is
    bound at all — refuses the decision. This is a fail-closed allowlist,
    not source tracking: ``Decision.content_origin`` is audit metadata only.

    Returns ``(missing_privileges, envelope_bound)`` when the decision is
    privileged and at least one grant is absent, else ``None``.
    Non-privileged decisions, and privileged decisions without tool calls
    (no privilege to check), are untouched.
    """
    if req is None or not req.required:
        return None
    tool_names = [
        call.tool_name
        for call in (decision.tool_calls or [])
        if isinstance(getattr(call, "tool_name", None), str) and call.tool_name
    ]
    if not tool_names:
        return None
    envelope = get_current_trust_envelope()
    missing = [name for name in tool_names if envelope is None or not envelope.grants(name)]
    if not missing:
        return None
    return (missing, envelope is not None)


def _route_refusal_to_evidence(
    decision: Decision,
    missing_privileges: list[str],
    envelope_bound: bool,
) -> None:
    """ADR-0292 C4 + section 10: route a grant-absence refusal to the evidence ledger.

    Mechanical wiring per the section-10 adjudication: resolve the ambient
    evidence pair exactly like ``safe_executor._resolve_evidence_pair`` and
    prepare the refusal payload (the blocked ungrantable action itself is the
    evidence). ``Decision.content_origin`` is recorded as audit metadata —
    "which external claim, if any, was present" — not as a trigger. The
    import is deferred so this module never takes a hard dependency on the
    observability stack at load time. No bound observability (unit tests /
    offline paths) -> no-ref path: refusal routing still holds, only the
    evidence copy is skipped.
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
    origin = decision.content_origin
    payload = json.dumps(
        {
            "event": "authorization_refusal",
            "gate": "act.approve.gate",
            "adr": "0292",
            "section": "10",
            "decision_id": decision.decision_id,
            "missing_grants": missing_privileges,
            "envelope_bound": envelope_bound,
            "content_origin": origin.value if origin is not None else None,
            "refused_at": datetime.now(UTC).isoformat(),
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

    The node is not a pure transform of its ports: beyond the typed
    ``decision`` / ``command`` / ``approval_requirement`` ports it reads two
    ambient seams. ADR-0292 section 10: before approval routing, a
    grant-absence gate refuses privileged actions whose tool privileges are
    absent from the ambient TrustEnvelope (ADR-0199, bound via
    ``trust_envelope_scope``) — fail-closed allowlist, ``content_origin``
    as audit metadata only. On the refused path only, the gate additionally
    routes the refusal payload to the run-trace evidence ledger through the
    ambient observability seam (same pattern as
    ``safe_executor._resolve_evidence_pair``; no-ref path when unbound) —
    ADR-0292 C4, "the blocked attack itself is security evidence".
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
      to abort cleanly. ADR-0292 section 10: also the routing for a
      refused grant-absence privilege claim — the ungrantable action never
      reaches ``act.envelope``; the refusal payload is routed to
      the run-trace evidence ledger (C4).
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

        # ADR-0292 section 10: grant-absence gate before approval routing.
        # A privileged action without a matching grant in the ambient
        # TrustEnvelope is refused outright — authorization comes only from
        # user grants (TrustEnvelope) + rule defaults, never from the
        # decision's own claims. No user interrupt is spent on an
        # ungrantable action. content_origin is audit metadata only.
        grant_refusal = _grant_absence_refusal(decision, req)
        if grant_refusal is not None:
            missing, envelope_bound = grant_refusal
            _route_refusal_to_evidence(decision, missing, envelope_bound)
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

        # The policy signal is authoritative when present; without it the
        # gate falls back to the model's self-reported
        # ``decision.needs_approval`` (§10 treats that fallback as
        # untrustworthy — the port is declared required so the bundle
        # wiring check fails loud at boot instead of degrading here).
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
