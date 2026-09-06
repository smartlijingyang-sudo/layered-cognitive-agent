"""FactGateway 单入口与 bound-session 语义测试(ADR-0194 P1-01/P1-02)。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.harness.tasks.session import session_event
from lca.loop.fact_gateway import (
    DefaultFactGateway,
    append_catalog_bound,
    fact_gateway_for_emit,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


@session_event("test.gateway.catalog.v1")
@dataclass(frozen=True)
class _GatewayCatalogPayload:
    kind: str
    value: int


def test_append_catalog_delegates_to_session() -> None:
    session = Session("t-bound-1")
    gateway = DefaultFactGateway(session)

    receipt = gateway.append_catalog(_GatewayCatalogPayload(kind="probe", value=7), actor="gate")

    assert session.event_count == 1
    event = session.event_at(0)
    assert event is not None
    assert event.type == "test.gateway.catalog.v1"
    assert event.actor == "gate"
    assert receipt.event_type == event.type
    assert receipt.seq == event.seq
    assert receipt.session_id == event.session_id
    assert receipt.time == event.time


def test_append_catalog_noop_when_session_unbound() -> None:
    assert fact_gateway_for_emit() is None
    assert append_catalog_bound(_GatewayCatalogPayload(kind="probe", value=1), actor="gate") is None


def test_append_catalog_bound_uses_publish_session() -> None:
    session = Session("t-bound-2")
    token = set_publish_session(session)
    try:
        receipt = append_catalog_bound(
            _GatewayCatalogPayload(kind="ctx", value=3), actor="perceive"
        )
        assert receipt is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "test.gateway.catalog.v1"
        assert event.actor == "perceive"
    finally:
        reset_publish_session(token)


def test_publish_ep_single_entry() -> None:
    session = Session("t-ep-1")
    gateway = DefaultFactGateway(session)

    receipt = gateway.publish_ep("brain.perceive.start", {"source": "probe"}, actor="gate")

    assert session.event_count == 1
    event = session.event_at(0)
    assert event is not None
    assert event.type == "spine.cognition.brain.perceive.start"
    assert receipt.event_type == event.type
    assert receipt.seq == event.seq


def test_publish_ep_unknown_raises() -> None:
    session = Session("t-ep-2")
    gateway = DefaultFactGateway(session)

    with pytest.raises(ValueError):
        gateway.publish_ep("not.a.real.ep", {}, actor="gate")

    assert session.event_count == 0


def test_append_diagnostic_noop() -> None:
    session = Session("t-diag-1")
    gateway = DefaultFactGateway(session)

    assert gateway.append_diagnostic(object()) is None
    assert session.event_count == 0


# --- cognitive_emit → FactGateway (ADR-0194 P1-06) ---


def test_cognitive_emit_gate_decided_returns_append_receipt() -> None:
    from lca.contracts.harness.fold.perceive import fold_gate_decisions_from_events
    from lca.contracts.models.core.policy.budget import create_budget
    from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
    from lca.infrastructure.session.emit.cognitive_emit import emit_gate_decided_from_policy

    session = Session("gate_gateway")
    state = AgentState(
        trace_id="trace:cognitive-emit-loop",
        task="test",
        budget=create_budget(max_steps=8),
        step=2,
    )
    receipt = emit_gate_decided_from_policy(
        state,
        GateDecided(
            event_id="gate-gw-1",
            gate="RepeatToolCallGate",
            verdict="warn",
            is_rewritten=False,
            policy_fact=PolicyFact(
                kind="repeat_tool_call",
                message="warning",
                source="repeat_tool_call",
            ),
        ),
        session=session,
    )

    assert isinstance(receipt, AppendReceipt)
    assert receipt.event_type == "gate.decided.v1"
    assert receipt.seq == 0
    assert receipt.session_id == session.id
    folded = fold_gate_decisions_from_events(session.snapshot_events(), step=2)
    assert len(folded) == 1
    assert folded[0].gate == "RepeatToolCallGate"
    assert folded[0].policy_fact is not None
    assert folded[0].policy_fact.kind == "repeat_tool_call"


def test_cognitive_emit_gate_decided_noop_when_unbound() -> None:
    from lca.contracts.models.core.policy.budget import create_budget
    from lca.contracts.models.core.policy.gate_policy import GateDecided
    from lca.contracts.models.core.state.state import AgentState
    from lca.infrastructure.session.emit.cognitive_emit import emit_gate_decided_from_policy

    state = AgentState(
        trace_id="trace:cognitive-emit-loop",
        task="test",
        budget=create_budget(max_steps=8),
        step=0,
    )
    assert (
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-gw-2",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
            ),
        )
        is None
    )


def test_cognitive_emit_context_manifested_via_gateway() -> None:
    from lca.contracts.harness.fold.perceive import fold_context_manifest_from_events
    from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
    from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
    from lca.infrastructure.session.emit.cognitive_emit import emit_context_manifested

    session = Session("manifest_gateway")
    manifest = ContextManifest(
        items=(
            ContextItem(
                kind="policy_fact",
                payload="loop warning",
                provenance="repeat_tool_call",
                extra={"kind": "repeat_tool_call", "gate": "RepeatToolCallGate"},
            ),
        ),
        digest="digest-gw",
    )

    receipt = emit_context_manifested(session, manifest, step=4, actor="perceive")

    assert isinstance(receipt, AppendReceipt)
    assert receipt.event_type == "context.manifested.v1"
    folded = fold_context_manifest_from_events(session.snapshot_events(), step=4)
    assert folded is not None
    assert folded.digest == "digest-gw"
    assert len(folded.items) == 1
    assert folded.items[0].kind == "policy_fact"
    assert folded.items[0].provenance == "repeat_tool_call"


def test_cognitive_emit_context_manifested_for_state_uses_bound_session() -> None:
    from lca.contracts.models.core.perceive.perception import ContextManifest
    from lca.contracts.models.core.policy.budget import create_budget
    from lca.contracts.models.core.state.state import AgentState
    from lca.infrastructure.session.emit.cognitive_emit import emit_context_manifested_for_state

    session = Session("manifest_bound")
    token = set_publish_session(session)
    try:
        state = AgentState(
            trace_id="trace:cognitive-emit-loop",
            task="test",
            budget=create_budget(max_steps=8),
            step=5,
        )
        manifest = ContextManifest(items=(), digest="bound-digest")
        receipt = emit_context_manifested_for_state(state, manifest)
        assert receipt is not None
        assert receipt.event_type == "context.manifested.v1"
        assert session.event_count == 1
    finally:
        reset_publish_session(token)


# --- transport_emit / agent_spawn_emit → FactGateway (ADR-0194 P5-01) ---


def test_transport_emit_all_categories_via_gateway() -> None:
    from lca.loop.transport import (
        emit_kernel_run_cancelled,
        emit_kernel_run_start,
        emit_kernel_run_stop,
        emit_transport_route_enter,
        emit_transport_route_exit,
        emit_transport_sse_publish,
    )

    session = Session("t-transport-emit")
    token = set_publish_session(session)
    try:
        ref = emit_transport_route_enter(path="/runs", method="POST", run_id="r1", session=session)
        assert ref is not None
        assert ref.category == "spine.transport.route.enter"
        ref = emit_transport_route_exit(path="/runs", method="POST", run_id="r1", session=session)
        assert ref is not None
        assert ref.category == "spine.transport.route.exit"
        ref = emit_transport_sse_publish(path="/events", run_id="r1", session=session)
        assert ref is not None
        assert ref.category == "spine.transport.sse.publish"
        ref = emit_kernel_run_start(run_id="r1", trace_id="t1", session=session)
        assert ref is not None
        assert ref.category == "spine.kernel.run.start"
        ref = emit_kernel_run_stop(run_id="r1", outcome="success", session=session)
        assert ref is not None
        assert ref.category == "spine.kernel.run.stop"
        ref = emit_kernel_run_cancelled(run_id="r1", session=session)
        assert ref is not None
        assert ref.category == "spine.kernel.run.cancelled"
        assert session.event_count == 6
    finally:
        reset_publish_session(token)


def test_agent_spawn_emit_iteration_via_gateway() -> None:
    from lca.loop.emit.cognitive.agent_spawn import (
        emit_agent_loop_iteration_end,
        emit_agent_loop_iteration_start,
    )

    session = Session("t-agent-spawn-emit")
    token = set_publish_session(session)
    try:
        start = emit_agent_loop_iteration_start(
            trace_id="trace-1",
            role="solo",
            iteration_kind="fresh",
            session=session,
        )
        assert start is not None
        assert start.category == "spine.agent_loop.iteration.start"
        end = emit_agent_loop_iteration_end(
            trace_id="trace-1",
            role="solo",
            iteration_kind="fresh",
            outcome="success",
            session=session,
        )
        assert end is not None
        assert end.category == "spine.agent_loop.iteration.end"
        assert session.event_count == 2
    finally:
        reset_publish_session(token)
