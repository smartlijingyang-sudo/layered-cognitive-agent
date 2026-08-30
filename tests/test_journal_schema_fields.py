"""Phase J — journal schema alignment (spec §24.5).

StampedEvent must carry the full Phase J schema:

- trace_id / parent_trace_id / run_id / delegation_id / agent_role
- turn / step / seq / ts
- event_type / data / correlation ids

RunStore.append must auto-fill ``event_type`` from
``type(event).__name__``.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from lca.contracts.models.observability.journal import (
    InboxFollowupCreated,
    RunScope,
    StampedEvent,
)
from lca.infrastructure.observability.journal.engine import RunStore


def _has_field(cls: type, name: str) -> bool:
    """Return True when ``cls`` (a dataclass) declares a field named ``name``."""
    assert is_dataclass(cls), f"{cls.__name__} must be a dataclass"
    return any(f.name == name for f in fields(cls))


class TestStampedEventFields:
    """Spec §24.5: every stamped event carries event_type + data + correlation_ids.

    ``turn`` 字段已删除（v3 永远 0，从未消费；测试覆盖缺失保护）。
    """

    def test_stamped_event_does_not_have_turn_field(self) -> None:
        assert not _has_field(StampedEvent, "turn"), "StampedEvent.turn 字段已删除；不要再加回来"

    def test_stamped_event_has_event_type_field(self) -> None:
        assert _has_field(StampedEvent, "event_type"), (
            "StampedEvent must declare an 'event_type' field (spec §24.5)"
        )

    def test_stamped_event_has_data_field(self) -> None:
        assert _has_field(StampedEvent, "data"), (
            "StampedEvent must declare a 'data' dict field (spec §24.5)"
        )

    def test_stamped_event_has_correlation_ids_field(self) -> None:
        assert _has_field(StampedEvent, "correlation_ids"), (
            "StampedEvent must declare a 'correlation_ids' tuple field"
        )


class TestRunScopeFields:
    """Spec §24.5: correlation skeleton must include parent_trace_id."""

    def test_run_scope_has_parent_trace_id_field(self) -> None:
        assert _has_field(RunScope, "parent_trace_id"), (
            "RunScope must declare a 'parent_trace_id' field"
        )

    def test_run_scope_parent_trace_id_defaults_to_none(self) -> None:
        scope = RunScope()
        assert scope.parent_trace_id is None

    def test_run_scope_existing_fields_intact(self) -> None:
        scope = RunScope(parent_trace_id="parent-1")
        assert scope.parent_trace_id == "parent-1"
        # Existing fields still work.
        assert scope.trace_id == ""
        assert scope.run_id == ""
        assert scope.parent_run_id is None
        assert scope.delegation_id is None
        assert scope.agent_role == ""


class TestRunStoreAppendStampsEventType:
    """RunStore.append must auto-fill event_type = type(event).__name__."""

    def test_run_store_appends_event_type_automatically(self) -> None:
        store = RunStore()
        stamped = store.append(
            InboxFollowupCreated(inbox_id="x", actor="user", target="t", priority="p")
        )
        assert stamped.event_type == "InboxFollowupCreated", (
            f"RunStore.append must auto-fill event_type; got {stamped.event_type!r}"
        )

    def test_run_store_appends_data_automatically(self) -> None:
        store = RunStore()
        stamped = store.append(
            InboxFollowupCreated(
                inbox_id="abc",
                actor="user",
                target="next_turn",
                priority="task",
            )
        )
        assert isinstance(stamped.data, dict)
        # data mirrors the event payload; inbox_id should be present.
        assert stamped.data.get("inbox_id") == "abc"

    def test_run_store_default_correlation_ids_empty(self) -> None:
        store = RunStore()
        stamped = store.append(
            InboxFollowupCreated(inbox_id="abc", actor="user", target="t", priority="p")
        )
        assert stamped.correlation_ids == ()

    def test_run_store_no_turn_field(self) -> None:
        """turn 字段已删除（永远 0，从未消费）。"""
        store = RunStore()
        stamped = store.append(
            InboxFollowupCreated(inbox_id="abc", actor="user", target="t", priority="p")
        )
        assert not hasattr(stamped, "turn") or "turn" not in stamped.__dataclass_fields__


class TestStampedEventBackwardsCompatible:
    """Old callers using only the first 4 fields still work."""

    def test_construction_with_only_required_fields(self) -> None:
        stamped = StampedEvent(
            seq=1,
            ts=0.0,
            scope=RunScope(),
            event=InboxFollowupCreated(inbox_id="x", actor="user", target="t", priority="p"),
        )
        assert stamped.event_type == ""
        assert stamped.data == {}
        assert stamped.correlation_ids == ()
