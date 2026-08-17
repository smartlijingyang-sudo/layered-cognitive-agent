"""Tests for lca.plugins.session_service."""

from __future__ import annotations

from types import SimpleNamespace

from lca.plugins.session_service import SessionService


def _event(event_type: str, data: dict) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, data=data)


class TestDeriveMessagesEmpty:
    def test_empty_events_returns_empty(self) -> None:
        svc = SessionService()
        assert svc.derive_messages([]) == []


class TestDeriveMessagesFullConversation:
    def test_user_assistant_tool(self) -> None:
        svc = SessionService()
        events = [
            _event("message.accepted.v1", {"role": "user", "content_ref": "Hello"}),
            _event(
                "assistant.responded.v1",
                {"turn": 1, "step": 1, "content": "Hi there"},
            ),
            _event(
                "tool.completed.v1",
                {"call_id": "call_1", "success": True, "result_ref": "result data"},
            ),
        ]
        messages = svc.derive_messages(events)
        assert messages == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "content": "result data", "tool_call_id": "call_1"},
        ]


class TestNonSurfaceEventsSkipped:
    def test_non_surface_events_filtered(self) -> None:
        svc = SessionService()
        events = [
            _event("turn.started.v1", {"turn": 1}),
            _event("step.started.v1", {"turn": 1, "step": 1}),
            _event("model.completed.v1", {"turn": 1, "step": 1, "usage": None}),
            _event("session.created.v1", {"profile": "default"}),
        ]
        assert svc.derive_messages(events) == []


class TestIsSurfaceEvent:
    def test_surface_events(self) -> None:
        svc = SessionService()
        assert svc.is_surface_event("message.accepted.v1") is True
        assert svc.is_surface_event("assistant.responded.v1") is True
        assert svc.is_surface_event("tool.completed.v1") is True

    def test_non_surface_events(self) -> None:
        svc = SessionService()
        assert svc.is_surface_event("turn.started.v1") is False
        assert svc.is_surface_event("step.started.v1") is False
        assert svc.is_surface_event("model.completed.v1") is False
        assert svc.is_surface_event("session.created.v1") is False


class TestDeriveEventMessage:
    def test_unknown_event_returns_none(self) -> None:
        svc = SessionService()
        assert svc.derive_event_message("unknown.event.v1", {}) is None

    def test_message_accepted_non_user_returns_none(self) -> None:
        svc = SessionService()
        assert (
            svc.derive_event_message("message.accepted.v1", {"role": "system", "content_ref": "x"})
            is None
        )
