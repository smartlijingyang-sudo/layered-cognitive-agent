"""Tests for the v3 diagnostic patterns (spec §24.5)."""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    ApprovalResolved,
    ContextManifested,
    GateDecided,
    InboxFollowupCreated,
    MemoryCommitted,
    ToolInvoked,
)
from lca.infrastructure.observability.diagnostics import (
    DiagnosePattern,
    diagnose,
    diagnose_approval_rejected,
    diagnose_loop_stuck,
    diagnose_memory_poisoned,
    diagnose_model_not_seen,
)
from lca.infrastructure.observability.journal.engine.engine import RunStore


def _state(store: RunStore, *events):
    for event in events:
        store.append(event)
    return store


class TestDiagnoseModelNotSeen:
    def test_missing_inbox(self) -> None:
        store = _state(RunStore())
        report = diagnose_model_not_seen(store, expected_kind="user_input")
        assert not report.ok
        assert any(f.severity == "medium" for f in report.findings)

    def test_missing_manifest(self) -> None:
        store = _state(
            RunStore(),
            InboxFollowupCreated(inbox_id="x", actor="user", target="next_turn", priority="task"),
        )
        report = diagnose_model_not_seen(store, expected_kind="user_input")
        assert not report.ok

    def test_manifest_missing_kind(self) -> None:
        store = _state(
            RunStore(),
            InboxFollowupCreated(inbox_id="x", actor="user", target="next_turn", priority="task"),
            ContextManifested(step=0, item_kinds=("clock",), digest="abc"),
        )
        report = diagnose_model_not_seen(store, expected_kind="user_input")
        assert not report.ok
        assert report.findings[0].severity == "medium"


class TestDiagnoseLoopStuck:
    def test_no_repeat_below_threshold(self) -> None:
        store = RunStore()
        for i in range(5):
            store.append(ToolInvoked(tool_name=f"tool_{i}", invocation_id=f"inv-{i}", ok=True))
        report = diagnose_loop_stuck(store, window=5)
        assert report.ok

    def test_repeat_without_warn(self) -> None:
        store = RunStore()
        for i in range(10):
            store.append(ToolInvoked(tool_name="some_tool", invocation_id=f"inv-{i}", ok=True))
        report = diagnose_loop_stuck(store, window=10)
        assert not report.ok
        assert "LoopBreaker may not be wired" in report.findings[0].summary

    def test_repeat_with_warn(self) -> None:
        store = RunStore()
        for i in range(10):
            store.append(ToolInvoked(tool_name="some_tool", invocation_id=f"inv-{i}", ok=True))
        store.append(
            GateDecided(gate="RepeatToolCallGate", verdict="warn", is_rewritten=False, step=9)
        )
        report = diagnose_loop_stuck(store, window=10)
        assert not report.ok
        assert any("Brain may not be reading" in f.summary for f in report.findings)


class TestDiagnoseMemoryPoisoned:
    def test_procedural_commit_flagged(self) -> None:
        store = _state(
            RunStore(),
            MemoryCommitted(layer="procedural", record_id="rec-1"),
        )
        report = diagnose_memory_poisoned(store)
        assert not report.ok

    def test_semantic_commit_clean(self) -> None:
        store = _state(
            RunStore(),
            MemoryCommitted(layer="semantic", record_id="rec-1"),
        )
        report = diagnose_memory_poisoned(store)
        assert report.ok


class TestDiagnoseApprovalRejected:
    def test_denied_approval(self) -> None:
        store = _state(
            RunStore(),
            ApprovalResolved(envelope_id="env-1", resolver="human", approved=False),
        )
        report = diagnose_approval_rejected(store)
        assert not report.ok
        assert "denied" in report.findings[0].summary

    def test_approved_approval_clean(self) -> None:
        store = _state(
            RunStore(),
            ApprovalResolved(envelope_id="env-1", resolver="human", approved=True),
        )
        report = diagnose_approval_rejected(store)
        assert report.ok


def test_diagnose_dispatch() -> None:
    store = RunStore()
    # Should not raise on each pattern.
    for pattern in DiagnosePattern:
        if pattern == DiagnosePattern.MODEL_NOT_SEEN:
            diagnose(store, pattern=pattern, expected_kind="clock")
        elif pattern == DiagnosePattern.LOOP_STUCK:
            diagnose(store, pattern=pattern, window=5)
        else:
            diagnose(store, pattern=pattern)
