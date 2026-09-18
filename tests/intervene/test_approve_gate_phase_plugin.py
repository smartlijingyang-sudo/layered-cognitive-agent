"""Tests for region:intervene.act_approve_gate plugin (PR-3.8.6).

Per `docs/superpowers/plans/2026-09-15-pr3.8.6-act-approve-gate.md` and
`docs/superpowers/specs/2026-09-15-pr3.8-borrowed-nodes-design.md` §2.6,
the gate is a typed-boundary node under ``region:intervene`` that
consumes the ``decision`` + ``command`` ports and emits
``decision`` + ``routing`` ports. Four cases pin:

  (1) ``decision.needs_approval=True`` + no command → interrupt path
      (``next_node="intervene.interrupt"``,
      ``next_hint="approve_interrupt"``).
  (2) ``decision.needs_approval`` is False → pass-through
      (``next_node="act.envelope"``, ``next_hint="approve_skipped"``).
  (3) ``command.kind in {"reject", "redirect"}`` (or
      ``command.kind == "resume"`` for timeout/abandon) → abort
      (``next_node="terminal.commit"``,
      ``next_hint="approve_rejected"``).
  (4) ``command.kind == "approve"`` → envelope
      (``next_node="act.envelope"``,
      ``next_hint="approve_approved"``).

ADR-0235 / PR-5: ``needs_approval`` is a typed field on
:class:`Decision` (added by L-2 / G-9 follow-through). The gate reads
typed ports only — the previous ``_resolve_port(context, name)`` graph
runtime peek is gone.

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


def _decision(*, needs_approval: bool = False) -> Decision:
    """Build a Decision for the test (dataclass — kwargs only).

    ADR-0235 / PR-5: ``needs_approval`` is now a typed field on
    Decision; ``extra`` smuggling is gone.
    """
    return Decision(
        decision_id="dec_gate_001",
        action_type="use_tool",
        rationale="needs gate",
        confidence=1.0,
        needs_approval=needs_approval,
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
    routing: RoutingDecision = output.port_values["approval_routing"]
    assert isinstance(routing, RoutingDecision)
    assert routing.next_node == "intervene.interrupt"
    assert routing.next_hint == "approve_interrupt"
    # Decision is forwarded unchanged — the gate does not mutate it.
    assert decision.needs_approval is True
    assert decision.decision_id == "dec_gate_001"


# ---------------------------------------------------------------------------
# Case 2: needs_approval=False → pass-through to act.envelope.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_needs_approval_false_passes_through_to_envelope() -> None:
    """``needs_approval=False`` → skip, route to envelope (skipped)."""
    executor = ApproveGateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": _decision(needs_approval=False)}),
    )
    routing: RoutingDecision = output.port_values["approval_routing"]
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
    routing: RoutingDecision = output.port_values["approval_routing"]
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
    routing: RoutingDecision = output.port_values["approval_routing"]
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
    routing: RoutingDecision = output.port_values["approval_routing"]
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
    routing: RoutingDecision = output.port_values["approval_routing"]
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
    assert out_a.port_values["approval_routing"] == out_b.port_values["approval_routing"]


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


def test_gate_resume_path_is_full_restart() -> None:
    """Full-restart HITL resume: no surgical resume nodes in outer graph.

    The HITL resume design restarts the graph from ``perceive.main``
    with the human answer folded into state (driver.py). The previous
    surgical-resume nodes (``act.resume``, ``intervene.resume``) and
    their edges were removed because they were dead code — the driver
    always points the cursor at ``perceive.main``.

    This guard pins the design: the outer YAML must NOT carry
    ``act.resume`` or ``intervene.resume`` nodes, and must have
    ``intervene.interrupt`` for the pause path.
    """
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parents[2]

    outer_spec = yaml.safe_load(
        (repo_root / "bundles" / "outer" / "phase_main.yaml").read_text(encoding="utf-8")
    )
    outer_nodes = outer_spec.get("nodes", ()) or ()
    node_ids = {n.get("id") for n in outer_nodes if isinstance(n, dict)}

    assert "act.resume" not in node_ids, (
        "act.resume node present in bundles/outer/phase_main.yaml; "
        "full-restart resume design removed it (driver.py restarts "
        "from perceive.main with the human answer folded into state)."
    )
    assert "intervene.resume" not in node_ids, (
        "intervene.resume node present in bundles/outer/phase_main.yaml; "
        "full-restart resume design removed it."
    )
    assert "intervene.interrupt" in node_ids, (
        "intervene.interrupt node missing from outer plan; "
        "the HITL pause path requires this node."
    )

    outer_edges = outer_spec.get("edges", ()) or ()
    resume_edges = [
        e for e in outer_edges
        if isinstance(e, dict)
        and (e.get("from") == "intervene.resume" or e.get("to") == "intervene.resume"
             or e.get("from") == "act.resume" or e.get("to") == "act.resume")
    ]
    assert not resume_edges, (
        "Edges referencing intervene.resume or act.resume present in "
        "outer plan; full-restart resume design removed them."
    )


def test_gate_consumed_by_outer_routing_edges() -> None:
    """The outer plan routes ``act.main.routing`` to the 3 HITL targets.

    ADR-0237 / PR-1b: gate emits a typed ``RoutingDecision`` that bubbles
    out of the subgraph via ``act.main.declared_outputs``. The outer plan
    owns three mutually-exclusive edges from ``act.main`` to
    ``{intervene.interrupt, terminal.commit, reflect.main}`` — one of
    the 4 ``next_hint`` values determines which target fires.
    """
    from pathlib import Path

    import yaml

    bundle_path = Path(__file__).resolve().parents[2] / "bundles" / "outer" / "phase_main.yaml"
    spec = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    edges = spec.get("edges", ()) or ()
    routing_edges = {
        e.get("to")
        for e in edges
        if isinstance(e, dict) and e.get("from") == "act.main"
    }
    for target in ("intervene.interrupt", "terminal.commit", "reflect.main"):
        assert target in routing_edges, (
            f"act.main → {target} missing from bundles/outer/phase_main.yaml — "
            f"the gate's routing hint has no outer consumer"
        )
