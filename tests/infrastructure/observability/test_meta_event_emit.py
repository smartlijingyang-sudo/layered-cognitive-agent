"""Meta-event emit helper tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from lca.infrastructure.observability.meta_event_emit import (
    emit_skill_loaded,
    emit_tool_schema_published,
    tool_registry_digest,
)
from lca.loop.fact_gateway import publish_ep_bound
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


@dataclass
class _FakeRecord:
    type: str
    seq: int
    session_id: str
    time: str = "2026-01-01T00:00:00Z"


class _FakeSession:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self._seq = 0

    def append(self, event_type: str, data: dict, **kwargs: Any) -> _FakeRecord:
        del kwargs
        self.events.append((event_type, data))
        self._seq += 1
        return _FakeRecord(type=event_type, seq=self._seq, session_id="fake")


def test_emit_tool_schema_published_with_session() -> None:
    from lca.infrastructure.observability import meta_event_emit as mod

    session = _FakeSession()
    original = mod.resolve_session_reader
    mod.resolve_session_reader = lambda: session  # type: ignore[method-assign, assignment]
    try:
        emit_tool_schema_published(("search_skill", "import_skill", "search_skill"))
    finally:
        mod.resolve_session_reader = original  # type: ignore[method-assign]

    assert len(session.events) == 1
    event_type, data = session.events[0]
    assert event_type == "tool.schema.published.v1"
    assert data["tool_names"] == ("import_skill", "search_skill")
    assert data["digest"] == tool_registry_digest(("import_skill", "search_skill"))


def test_tool_registry_digest_stable() -> None:
    d1 = tool_registry_digest(("a", "b"))
    d2 = tool_registry_digest(("b", "a"))
    assert d1 == d2


def test_emit_without_session_logs() -> None:
    ref = emit_skill_loaded(skill_id="x", content_hash="h")
    assert ref is None


def test_meta_emit_catalog_uses_gateway() -> None:
    session = Session("t-meta-gateway")
    token = set_publish_session(session)
    try:
        with patch("lca.loop.fact_gateway.DefaultFactGateway.append_catalog") as gateway_append:
            emit_tool_schema_published(("search_skill",))
        gateway_append.assert_called_once()
    finally:
        reset_publish_session(token)


def test_meta_emit_catalog_writes_session() -> None:
    session = Session("t-meta-write")
    token = set_publish_session(session)
    try:
        emit_tool_schema_published(("import_skill",))
        events = [
            event for event in session.snapshot_events() if event.type == "tool.schema.published.v1"
        ]
        assert len(events) == 1
    finally:
        reset_publish_session(token)


def test_meta_emit_skill_spine_uses_publish_ep_bound() -> None:
    session = Session("t-meta-spine")
    token = set_publish_session(session)
    try:
        with patch(
            "lca.infrastructure.observability.meta_event_emit.publish_ep_bound",
            wraps=publish_ep_bound,
        ) as publish_ep:
            emit_skill_loaded(skill_id="skill-a", content_hash="hash-a")
        assert publish_ep.call_count == 1
        catalog = [event for event in session.snapshot_events() if event.type == "skill.loaded.v1"]
        assert len(catalog) == 1
    finally:
        reset_publish_session(token)
