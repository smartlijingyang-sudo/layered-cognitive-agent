"""Session thinking.* 词表契约 —— 注册类型、可见性与字段形态。"""

from __future__ import annotations

from lca.contracts.harness.memory.events import ThinkingCompleted, ThinkingDelta
from lca.contracts.harness.tasks.session import event_registry, event_type_of


def test_thinking_events_register_with_expected_types() -> None:
    assert ThinkingDelta._event_type == "thinking.delta.v1"
    assert ThinkingCompleted._event_type == "thinking.completed.v1"


def test_thinking_events_are_audit_visibility() -> None:
    assert ThinkingDelta._visibility == "audit"
    assert ThinkingCompleted._visibility == "audit"


def test_thinking_events_present_in_registry() -> None:
    registry = event_registry()
    assert registry["thinking.delta.v1"] is ThinkingDelta
    assert registry["thinking.completed.v1"] is ThinkingCompleted


def test_event_type_of_resolves_payload_instances() -> None:
    delta = ThinkingDelta(turn=1, step=2, text_delta="x")
    done = ThinkingCompleted(turn=1, step=2, duration_ms=3, content_preview="x")
    assert event_type_of(delta) == "thinking.delta.v1"
    assert event_type_of(done) == "thinking.completed.v1"


def test_thinking_delta_seq_defaults_to_zero() -> None:
    assert ThinkingDelta(turn=0, step=0, text_delta="x").seq == 0
