"""Tests for plan_ref × Journal 绑定 (ADR-0074 PR-6 + acceptance §3.3 V5).

This test covers:

- StampedEvent.plan_ref field (auto-stamped from ContextVar)
- set_current_plan_ref / get_current_plan_ref / plan_ref_scope helpers
- RunStore.append() reads plan_ref from ContextVar at append time
- JournalRecord.plan_ref serializes to v2 envelope + round-trips
- Empty plan_ref = legacy path (tests / projector previews)
"""

from __future__ import annotations

import pytest

from lca.contracts.models.observability.event import (
    OperationOutcome,
)
from lca.contracts.models.observability.journal import (
    JournalRecord,
    RuntimeObserved,
    StampedEvent,
    stamped_to_journal_record,
)
from lca.contracts.models.observability.plan_ref import (
    get_current_plan_ref,
    plan_ref_scope,
    reset_current_plan_ref,
    set_current_plan_ref,
    stamped_event_has_plan_ref,
)

# ── plan_ref module helpers ──────────────────────────────────────────


class TestGetCurrentPlanRef:
    def test_default_is_empty_string(self) -> None:
        """未 set plan_ref → 默认 ``""``（legacy 兼容路径）。"""
        # Reset to make sure no other test left state
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )

        token = _run_plan_ref.set("__test_marker__")
        try:
            assert get_current_plan_ref() == "__test_marker__"
            _run_plan_ref.reset(token)
            assert get_current_plan_ref() == ""
        except Exception:
            _run_plan_ref.reset(token)
            raise


class TestSetCurrentPlanRef:
    def test_set_and_get(self) -> None:
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )

        prior = _run_plan_ref.set("__prior__")
        try:
            token = set_current_plan_ref("abc123")
            assert get_current_plan_ref() == "abc123"
            reset_current_plan_ref(token)
            assert get_current_plan_ref() == "__prior__"
            _run_plan_ref.reset(prior)
        except Exception:
            _run_plan_ref.reset(prior)
            raise

    def test_set_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            set_current_plan_ref("")


class TestPlanRefScope:
    def test_with_block_sets_plan_ref(self) -> None:
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )

        prior = _run_plan_ref.set("__prior__")
        try:
            with plan_ref_scope("xyz789") as ref:
                assert ref == "xyz789"
                assert get_current_plan_ref() == "xyz789"
            # After with-block: restored to prior
            assert get_current_plan_ref() == "__prior__"
            _run_plan_ref.reset(prior)
        except Exception:
            _run_plan_ref.reset(prior)
            raise

    def test_with_block_restores_on_exception(self) -> None:
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )

        prior = _run_plan_ref.set("__prior__")
        try:
            with pytest.raises(RuntimeError), plan_ref_scope("temp_ref"):
                raise RuntimeError("boom")
            assert get_current_plan_ref() == "__prior__"
            _run_plan_ref.reset(prior)
        except Exception:
            _run_plan_ref.reset(prior)
            raise


class TestStampedEventHasPlanRef:
    def test_empty_returns_false(self) -> None:
        assert stamped_event_has_plan_ref("") is False

    def test_non_empty_returns_true(self) -> None:
        assert stamped_event_has_plan_ref("abc123") is True


# ── StampedEvent.plan_ref field ───────────────────────────────────────


class TestStampedEventPlanRefField:
    def test_default_is_empty_string(self) -> None:
        """StampedEvent.plan_ref 默认 = ""（向后兼容）。"""
        event = RuntimeObserved(
            operation="test.op",
            source="test",
            outcome=OperationOutcome.OK,
        )
        stamped = StampedEvent(
            seq=1,
            ts=0.0,
            scope=None,
            event=event,
            event_type="RuntimeObserved",
        )
        assert stamped.plan_ref == ""

    def test_plan_ref_can_be_set(self) -> None:
        event = RuntimeObserved(
            operation="test.op",
            source="test",
            outcome=OperationOutcome.OK,
        )
        stamped = StampedEvent(
            seq=1,
            ts=0.0,
            scope=None,
            event=event,
            event_type="RuntimeObserved",
            plan_ref="my_plan_ref_1234",
        )
        assert stamped.plan_ref == "my_plan_ref_1234"


# ── RunStore.append auto-stamps plan_ref ────────────────────────────


class TestRunStoreAppendStampsPlanRef:
    def test_append_inherits_plan_ref_from_context(self) -> None:
        """RunStore.append reads plan_ref from ContextVar at append time."""
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )
        from lca.infrastructure.observability.journal.engine import RunStore

        prior = _run_plan_ref.set("__prior__")
        try:
            store = RunStore()
            event = RuntimeObserved(
                operation="test.op",
                source="test",
                outcome=OperationOutcome.OK,
            )
            with plan_ref_scope("run_plan_ref_xyz"):
                stamped = store.append(event)
            assert stamped.plan_ref == "run_plan_ref_xyz"
            _run_plan_ref.reset(prior)
        except Exception:
            _run_plan_ref.reset(prior)
            raise

    def test_append_no_plan_ref_when_unset(self) -> None:
        """未 set plan_ref → StampedEvent.plan_ref = ""（legacy 兼容）。"""
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )
        from lca.infrastructure.observability.journal.engine import RunStore

        prior = _run_plan_ref.set("__prior__")
        try:
            _run_plan_ref.reset(prior)
            store = RunStore()
            event = RuntimeObserved(
                operation="test.op",
                source="test",
                outcome=OperationOutcome.OK,
            )
            stamped = store.append(event)
            assert stamped.plan_ref == ""
        finally:
            pass


# ── JournalRecord plan_ref round-trip ───────────────────────────────


class TestJournalRecordPlanRef:
    def test_default_is_empty_string(self) -> None:
        record = JournalRecord()
        assert record.plan_ref == ""

    def test_to_dict_includes_plan_ref(self) -> None:
        record = JournalRecord(plan_ref="abc123")
        d = record.to_dict()
        assert "plan_ref" in d
        assert d["plan_ref"] == "abc123"

    def test_from_dict_round_trips_plan_ref(self) -> None:
        original = JournalRecord(plan_ref="round_trip_xyz")
        d = original.to_dict()
        restored = JournalRecord.from_dict(d)
        assert restored.plan_ref == "round_trip_xyz"

    def test_from_dict_defaults_plan_ref_when_missing(self) -> None:
        """旧 v2 envelope 不含 plan_ref 字段 → 解析时 default ""。"""
        d = {
            "schema": "lca.journal/2",
            "event_id": "evt_test",
            "run_id": "run_test",
            "run_seq": 1,
            "occurred_at": 0.0,
            "committed_at": 0.0,
            "scope": {},
            "causation": {"parent_event_id": "", "links": []},
            "descriptor": {"type": "RuntimeObserved", "version": 1, "payload_schema_version": 1},
            "data": {},
            "evidence": [],
            # No plan_ref key — legacy envelope
        }
        record = JournalRecord.from_dict(d)
        assert record.plan_ref == ""


# ── stamped_to_journal_record propagates plan_ref ───────────────────


class TestStampedToJournalRecordPropagatesPlanRef:
    def test_plan_ref_propagates_to_journal_record(self) -> None:
        event = RuntimeObserved(
            operation="test.op",
            source="test",
            outcome=OperationOutcome.OK,
        )
        stamped = StampedEvent(
            seq=1,
            ts=0.0,
            scope=None,
            event=event,
            event_type="RuntimeObserved",
            plan_ref="xyz_plan_ref",
        )
        record = stamped_to_journal_record(
            stamped,
            event_id="evt_1",
            run_id="run_1",
            run_seq=1,
            occurred_at=0.0,
            committed_at=0.0,
        )
        assert record.plan_ref == "xyz_plan_ref"

    def test_empty_plan_ref_propagates(self) -> None:
        event = RuntimeObserved(
            operation="test.op",
            source="test",
            outcome=OperationOutcome.OK,
        )
        stamped = StampedEvent(
            seq=1,
            ts=0.0,
            scope=None,
            event=event,
            event_type="RuntimeObserved",
        )
        record = stamped_to_journal_record(
            stamped,
            event_id="evt_1",
            run_id="run_1",
            run_seq=1,
            occurred_at=0.0,
            committed_at=0.0,
        )
        assert record.plan_ref == ""


# ── V5 acceptance: every fact carries plan_ref in a run ────────────


class TestV5AcceptanceEveryFactCarriesPlanRef:
    def test_run_with_plan_ref_every_event_stamped(self) -> None:
        """V5 硬约束：跑 1 个完整 run → 每条 StampedEvent 携带 plan_ref。

        用 RunStore + plan_ref_scope 模拟完整 run：
        - 多条 events 连续 append
        - 每条都应携带 plan_ref（active ContextVar）
        - plan_ref 全为同一值（同 run）
        """
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )
        from lca.infrastructure.observability.journal.engine import RunStore

        prior = _run_plan_ref.set("__prior__")
        try:
            store = RunStore(run_id="run_v5_test")
            events_emitted = [
                RuntimeObserved(
                    operation=f"op_{i}",
                    source="v5_test",
                    outcome=OperationOutcome.OK,
                )
                for i in range(5)
            ]
            with plan_ref_scope("v5_plan_ref"):
                stamped_events = [store.append(e) for e in events_emitted]

            # V5 acceptance: every fact carries plan_ref
            for stamped in stamped_events:
                assert stamped.plan_ref == "v5_plan_ref", (
                    f"V5 violation: StampedEvent seq={stamped.seq} "
                    f"has plan_ref={stamped.plan_ref!r}, expected 'v5_plan_ref'"
                )
            _run_plan_ref.reset(prior)
        except Exception:
            _run_plan_ref.reset(prior)
            raise

    def test_run_without_plan_ref_events_have_empty(self) -> None:
        """legacy path：未 set plan_ref → events.plan_ref = ""。"""
        from lca.contracts.models.observability.plan_ref import (
            _run_plan_ref,
        )
        from lca.infrastructure.observability.journal.engine import RunStore

        prior = _run_plan_ref.set("__prior__")
        try:
            _run_plan_ref.reset(prior)
            store = RunStore(run_id="run_legacy_test")
            events = [
                RuntimeObserved(
                    operation=f"op_{i}",
                    source="legacy_test",
                    outcome=OperationOutcome.OK,
                )
                for i in range(3)
            ]
            stamped_events = [store.append(e) for e in events]

            # Legacy path: empty plan_ref
            for stamped in stamped_events:
                assert stamped.plan_ref == ""
        finally:
            pass

    def test_plan_ref_change_mid_run_records_both(self) -> None:
        """plan_ref 在 run 中变更：先 set A 再 set B → 后续 events 携带 B。"""
        from lca.infrastructure.observability.journal.engine import RunStore

        store = RunStore(run_id="run_mid_change")
        event = RuntimeObserved(
            operation="op",
            source="mid_change",
            outcome=OperationOutcome.OK,
        )

        with plan_ref_scope("plan_A"):
            stamped_a = store.append(event)
        with plan_ref_scope("plan_B"):
            stamped_b = store.append(event)

        assert stamped_a.plan_ref == "plan_A"
        assert stamped_b.plan_ref == "plan_B"
