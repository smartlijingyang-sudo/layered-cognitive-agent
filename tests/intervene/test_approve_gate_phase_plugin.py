"""Tests for region:intervene.act_approve_gate plugin (PR-3.8.6).

Per `docs/superpowers/plans/2026-09-15-pr3.8.6-act-approve-gate.md` and
`docs/superpowers/specs/2026-09-15-pr3.8-borrowed-nodes-design.md` §2.6,
the gate is a typed-boundary node under ``region:intervene`` that
consumes the ``decision`` + ``command`` ports and emits
``decision`` + ``routing`` ports. Four cases pin:

  (1) ``decision.extra["needs_approval"]=True`` + no command → interrupt
      path (``next_node="intervene.interrupt"``,
      ``next_hint="approve_interrupt"``).
  (2) ``decision.extra["needs_approval"]`` absent or False →
      pass-through (``next_node="act.envelope"``,
      ``next_hint="approve_skipped"``).
  (3) ``command.kind in {"reject", "redirect"}`` (or
      ``command.kind == "resume"`` for timeout/abandon) → abort
      (``next_node="terminal.commit"``,
      ``next_hint="approve_rejected"``).
  (4) ``command.kind == "approve"`` → envelope
      (``next_node="act.envelope"``,
      ``next_hint="approve_approved"``).

Idempotency is verified by re-running the same input and asserting the
typed outputs are equal. The fail-closed contract (missing
``approval_resume_node`` edge) lives at the bundle-validate layer and
is covered by the per-PR verification matrix; this file focuses on
the typed-boundary executor surface.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.intervene.approve_gate import ApproveGateExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; the gate is a pure transform of input ports."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _decision(*, needs_approval: bool | None = False) -> Decision:
    """Build a Decision for the test (dataclass — kwargs only)."""
    extra: dict[str, object] = {}
    if needs_approval is not None:
        extra["needs_approval"] = needs_approval
    return Decision(
        decision_id="dec_gate_001",
        action_type="use_tool",
        rationale="needs gate",
        confidence=1.0,
        extra=extra,
    )


def _cmd(
    kind: str,
    *,
    payload: dict | None = None,
    issued_by: str = "user",
    issued_at_seq: int = 7,
) -> Command:
    """Build a Command for the test (Pydantic frozen — kwargs only)."""
    return Command(
        kind=kind,  # type: ignore[arg-type]
        payload=payload,
        issued_by=issued_by,
        issued_at_seq=issued_at_seq,
    )


# ---------------------------------------------------------------------------
# Case 1: needs_approval=True and no command → interrupt path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_needs_approval_without_command_routes_to_interrupt() -> None:
    """``needs_approval=True`` + ``command is None`` →
    ``next_node="intervene.interrupt"``, ``next_hint="approve_interrupt"``.
    """
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": _decision(needs_approval=True), "command": None}),
    )
    decision: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]
    assert isinstance(routing, RoutingDecision)
    assert routing.next_node == "intervene.interrupt"
    assert routing.next_hint == "approve_interrupt"
    # Decision is forwarded unchanged — the gate does not mutate it.
    assert decision.extra["needs_approval"] is True
    assert decision.decision_id == "dec_gate_001"


# ---------------------------------------------------------------------------
# Case 2: needs_approval absent or False → pass-through to act.envelope.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_needs_approval_absent_passes_through_to_envelope() -> None:
    """``decision.extra`` lacks ``needs_approval`` → skip, route to envelope."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": _decision(needs_approval=None)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "act.envelope"
    assert routing.next_hint == "approve_skipped"


@pytest.mark.asyncio
async def test_gate_needs_approval_false_passes_through_to_envelope() -> None:
    """``needs_approval=False`` → skip, route to envelope (skipped)."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": _decision(needs_approval=False)}),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "act.envelope"
    assert routing.next_hint == "approve_skipped"


# ---------------------------------------------------------------------------
# Case 3: reject / redirect / resume (timeout) → abort (terminal.commit).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_reject_routes_to_terminal_commit() -> None:
    """``command.kind == "reject"`` → terminal.commit (approve_rejected)."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("reject"),
            }
        ),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "approve_rejected"


@pytest.mark.asyncio
async def test_gate_redirect_to_abandon_routes_to_terminal_commit() -> None:
    """``command.kind == "redirect"`` (treated as abandon) → terminal.commit."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("redirect"),
            }
        ),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "approve_rejected"


@pytest.mark.asyncio
async def test_gate_resume_treated_as_timeout_routes_to_terminal_commit() -> None:
    """``command.kind == "resume"`` (timeout/abandon) → terminal.commit.

    Per spec §2.6 timeout / abandon aborts and never slips into
    ``act.envelope``. A bare ``resume`` without an explicit approve is
    treated as the timeout/abandon signal.
    """
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("resume"),
            }
        ),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "approve_rejected"


# ---------------------------------------------------------------------------
# Case 4: approve → envelope (approved); idempotency across instances.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_approve_routes_to_envelope() -> None:
    """``command.kind == "approve"`` → envelope (approve_approved)."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("approve"),
            }
        ),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "act.envelope"
    assert routing.next_hint == "approve_approved"


@pytest.mark.asyncio
async def test_gate_is_idempotent_across_instances() -> None:
    """Same input twice ⇒ same typed outputs (idempotent, deterministic).

    Two fresh executors with identical inputs must produce equal
    ``decision`` and ``routing`` ports. The gate carries no
    instance-level state that leaks into subsequent outputs.
    """
    inp = NodeInput(
        port_values={
            "decision": _decision(needs_approval=True),
            "command": _cmd("approve"),
        }
    )
    out_a = await ApproveGateExecutor().node_execute(_ctx(), inp)
    out_b = await ApproveGateExecutor().node_execute(_ctx(), inp)
    assert out_a.port_values["decision"] == out_b.port_values["decision"]
    assert out_a.port_values["routing"] == out_b.port_values["routing"]


# ---------------------------------------------------------------------------
# Type contract: invalid ports fail loud at the seam.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_rejects_non_decision_port() -> None:
    """Non-``Decision`` on ``decision`` port raises ``TypeError`` at the seam."""
    executor = ApproveGateExecutor()
    with pytest.raises(TypeError, match=r"act\.approve\.gate"):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"decision": {"not": "a decision"}}),
        )


@pytest.mark.asyncio
async def test_gate_rejects_non_command_port() -> None:
    """Non-``Command`` (and non-None) on ``command`` port raises ``TypeError``."""
    executor = ApproveGateExecutor()
    with pytest.raises(TypeError, match=r"act\.approve\.gate"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "decision": _decision(needs_approval=True),
                    "command": "not-a-command",
                }
            ),
        )


# ---------------------------------------------------------------------------
# Fail-closed: bundle wiring must keep the gate reachable from the entry.
# Verified at plan-lift time via ``validate_profile_plans`` — a missing
# ``intervene.resume → act.approve.gate`` resume edge leaves the gate
# unreachable and ``PlanLiftError`` fires (per plan §Task 1 acceptance).
# ---------------------------------------------------------------------------


def test_gate_resume_edge_is_present_in_outer_plan() -> None:
    """The ``intervene.resume → act.approve.gate`` resume edge is wired.

    Reads ``bundles/outer/phase_main.yaml`` directly and asserts the
    resume edge exists with the expected source/target. If a future
    PR removes the edge, plan validation would fail at boot with an
    unreachable-node error, so this is a static guard against that.
    """
    from pathlib import Path

    import yaml

    bundle_path = Path(__file__).resolve().parents[2] / "bundles" / "outer" / "phase_main.yaml"
    spec = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    edges = spec.get("edges", ()) or ()
    resume_edges = [
        e
        for e in edges
        if isinstance(e, dict)
        and e.get("from") == "intervene.resume"
        and e.get("to") == "act.approve.gate"
    ]
    assert resume_edges, (
        "intervene.resume → act.approve.gate resume edge missing from "
        "bundles/outer/phase_main.yaml — plan lift will fail at boot "
        "(approve gate unreachable from resume path)"
    )


def test_gate_reachable_from_act_main_in_outer_plan() -> None:
    """``act.main → act.approve.gate`` entry edge is wired.

    The gate is positioned in the flow between ``act.main`` and the
    next phase; without this edge the gate is unreachable and plan
    lift fails at boot.
    """
    from pathlib import Path

    import yaml

    bundle_path = Path(__file__).resolve().parents[2] / "bundles" / "outer" / "phase_main.yaml"
    spec = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    edges = spec.get("edges", ()) or ()
    entry_edges = [
        e
        for e in edges
        if isinstance(e, dict) and e.get("from") == "act.main" and e.get("to") == "act.approve.gate"
    ]
    assert entry_edges, (
        "act.main → act.approve.gate entry edge missing from "
        "bundles/outer/phase_main.yaml — plan lift will fail at boot "
        "(approve gate unreachable from act subgraph completion)"
    )
