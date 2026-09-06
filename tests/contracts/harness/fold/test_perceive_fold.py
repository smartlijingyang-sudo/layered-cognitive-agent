"""Pure fold tests for gate/context Session SSOT events (ADR-0191 R1)."""

from __future__ import annotations

from lca.contracts.harness.fold.perceive import (
    fold_context_manifest_from_events,
    fold_gate_decisions_from_events,
    fold_policy_facts_from_events,
)
from lca.contracts.harness.memory.events import ContextManifestCommitted, GateDecidedCommitted
from lca.contracts.harness.tasks.session import SessionEvent, event_type_of
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact


def _event(seq: int, event_type: str, data: dict) -> SessionEvent:
    return SessionEvent(
        session_id="s1",
        seq=seq,
        type=event_type,
        time=seq,
        data=data,
        visibility="model",
    )


def test_gate_and_context_events_register_with_expected_types() -> None:
    assert GateDecidedCommitted._event_type == "gate.decided.v1"
    assert ContextManifestCommitted._event_type == "context.manifested.v1"
    assert GateDecidedCommitted._visibility == "model"
    assert ContextManifestCommitted._visibility == "model"


def test_event_type_of_resolves_gate_and_context_payloads() -> None:
    gate = GateDecidedCommitted(
        event_id="g1",
        gate="RepeatToolCallGate",
        verdict="warn",
        is_rewritten=False,
        step=1,
        policy_fact_kind="repeat_tool_call",
        policy_fact_message="stop repeating",
        policy_fact_source="repeat_tool_call",
    )
    manifest = ContextManifestCommitted(step=2, digest="abc123", items=())
    assert event_type_of(gate) == "gate.decided.v1"
    assert event_type_of(manifest) == "context.manifested.v1"


def test_fold_gate_decisions_from_events_filters_by_step() -> None:
    events = (
        _event(
            0,
            "gate.decided.v1",
            {
                "event_id": "g0",
                "gate": "RepeatToolCallGate",
                "verdict": "warn",
                "is_rewritten": False,
                "step": 0,
                "policy_fact_kind": "repeat_tool_call",
                "policy_fact_message": "step 0",
                "policy_fact_source": "repeat_tool_call",
            },
        ),
        _event(
            1,
            "gate.decided.v1",
            {
                "event_id": "g1",
                "gate": "ToolLoopBreakerGate",
                "verdict": "rewrite",
                "is_rewritten": True,
                "step": 1,
                "tool_name": "search",
                "policy_fact_kind": "tool_loop_break",
                "policy_fact_message": "forced respond",
                "policy_fact_source": "tool_loop_breaker",
            },
        ),
    )

    step0 = fold_gate_decisions_from_events(events, step=0)
    step1 = fold_gate_decisions_from_events(events, step=1)

    assert len(step0) == 1
    assert step0[0] == GateDecided(
        event_id="g0",
        gate="RepeatToolCallGate",
        verdict="warn",
        is_rewritten=False,
        policy_fact=PolicyFact(
            kind="repeat_tool_call",
            message="step 0",
            source="repeat_tool_call",
        ),
    )
    assert len(step1) == 1
    assert step1[0].tool_name == "search"
    assert step1[0].verdict == "rewrite"


def test_fold_policy_facts_from_events_accumulates_through_step() -> None:
    events = (
        _event(
            0,
            "gate.decided.v1",
            {
                "event_id": "g0",
                "gate": "RepeatToolCallGate",
                "verdict": "warn",
                "is_rewritten": False,
                "step": 0,
                "policy_fact_kind": "repeat_tool_call",
                "policy_fact_message": "first",
                "policy_fact_source": "repeat_tool_call",
            },
        ),
        _event(
            1,
            "gate.decided.v1",
            {
                "event_id": "g1",
                "gate": "ToolLoopBreakerGate",
                "verdict": "rewrite",
                "is_rewritten": True,
                "step": 2,
                "policy_fact_kind": "tool_loop_break",
                "policy_fact_message": "second",
                "policy_fact_source": "tool_loop_breaker",
            },
        ),
        _event(
            2,
            "gate.decided.v1",
            {
                "event_id": "g2",
                "gate": "TerminalRespondGate",
                "verdict": "rewrite",
                "is_rewritten": True,
                "step": 3,
                "policy_fact_kind": "terminal_respond",
                "policy_fact_message": "third",
                "policy_fact_source": "terminal_respond",
            },
        ),
    )

    through_one = fold_policy_facts_from_events(events, through_step=1)
    through_two = fold_policy_facts_from_events(events, through_step=2)

    assert through_one == [
        PolicyFact(kind="repeat_tool_call", message="first", source="repeat_tool_call"),
    ]
    assert through_two == [
        PolicyFact(kind="repeat_tool_call", message="first", source="repeat_tool_call"),
        PolicyFact(kind="tool_loop_break", message="second", source="tool_loop_breaker"),
    ]


def test_fold_policy_facts_skips_gate_events_without_policy_fact() -> None:
    events = (
        _event(
            0,
            "gate.decided.v1",
            {
                "event_id": "g0",
                "gate": "NoFactGate",
                "verdict": "deny",
                "is_rewritten": False,
                "step": 0,
            },
        ),
    )

    assert fold_policy_facts_from_events(events, through_step=0) == []


def test_fold_context_manifest_from_events_returns_latest_for_step() -> None:
    events = (
        _event(
            0,
            "context.manifested.v1",
            {
                "step": 1,
                "digest": "old",
                "items": [
                    {
                        "kind": "clock",
                        "payload_repr": "'09:00'",
                        "provenance": "clock_sensor",
                        "extra": {},
                    }
                ],
            },
        ),
        _event(
            1,
            "context.manifested.v1",
            {
                "step": 1,
                "digest": "new",
                "items": [
                    {
                        "kind": "policy_fact",
                        "payload_repr": "'stop repeating'",
                        "provenance": "repeat_tool_call",
                        "extra": {"kind": "repeat_tool_call", "gate": "RepeatToolCallGate"},
                    }
                ],
            },
        ),
        _event(
            2,
            "context.manifested.v1",
            {
                "step": 2,
                "digest": "other",
                "items": [],
            },
        ),
    )

    manifest = fold_context_manifest_from_events(events, step=1)

    assert manifest == ContextManifest(
        digest="new",
        items=(
            ContextItem(
                kind="policy_fact",
                payload="'stop repeating'",
                provenance="repeat_tool_call",
                extra={"kind": "repeat_tool_call", "gate": "RepeatToolCallGate"},
            ),
        ),
    )
    assert fold_context_manifest_from_events(events, step=99) is None
