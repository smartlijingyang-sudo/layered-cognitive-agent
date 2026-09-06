"""Meta-event emit helper tests."""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.observability.meta_event_emit import (
    emit_tool_schema_published,
    tool_registry_digest,
)


class _FakeSession:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type: str, data: dict, **kwargs: Any) -> Any:
        del kwargs
        self.events.append((event_type, data))
        return object()


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
    from lca.infrastructure.observability.meta_event_emit import emit_skill_loaded

    ref = emit_skill_loaded(skill_id="x", content_hash="h")
    assert ref is None
