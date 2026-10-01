"""Tests for ToolDeferSession (lca.infrastructure.tool_defer.session)."""

from __future__ import annotations

import json
from typing import Any

from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    current_defer_session,
    reset_current_defer_session,
    set_current_defer_session,
)


class FakeTool:
    """Minimal structural Tool: name/description/parameters + execute."""

    def __init__(self, name: str, params: dict[str, Any] | None = None) -> None:
        self.name = name
        self.description = f"fake tool {name}"
        self.parameters = params or {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _tools() -> tuple[FakeTool, ...]:
    return (
        FakeTool("tool_search"),
        FakeTool("core_a"),
        FakeTool("b_one"),
        FakeTool("b_two"),
    )


def _namespaces() -> dict[str, str]:
    return {
        "tool_search": "tool_search",
        "core_a": "core",
        "b_one": "browser",
        "b_two": "browser",
    }


def _session(**policy_kw: Any) -> ToolDeferSession:
    return ToolDeferSession(DeferPolicy(**policy_kw))


def _wire_names(wire: tuple[dict[str, Any], ...]) -> list[str]:
    return [spec["function"]["name"] for spec in wire]


# --- render_turn: first-turn projection ------------------------------------


def test_first_turn_injects_only_eager_schemas() -> None:
    session = _session()
    session.update_turn(_tools(), _namespaces())
    wire, catalog = session.render_turn()
    # tool_search is the only eager namespace by default.
    assert _wire_names(wire) == ["tool_search"]
    assert "browser" in catalog
    assert "core" in catalog


def test_unloaded_namespace_schemas_never_leak_into_catalog() -> None:
    """Audit: full parameters of unloaded namespaces must not appear in
    the catalog text — otherwise the token saving is an illusion."""
    session = _session()
    tools = _tools()
    session.update_turn(tools, _namespaces())
    _, catalog = session.render_turn()
    for tool in tools:
        if tool.name != "tool_search":
            assert json.dumps(tool.parameters) not in catalog
    # No per-tool schema fragment at all — only one-liners.
    assert '"properties"' not in catalog


def test_deferred_wire_is_smaller_than_full_wire() -> None:
    session = _session()
    tools = _tools()
    session.update_turn(tools, _namespaces())
    wire, _ = session.render_turn()
    full = json.dumps([_tool_wire_spec(t) for t in tools])
    assert len(json.dumps(list(wire))) < len(full)


def _tool_wire_spec(tool: FakeTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


# --- load_namespace ---------------------------------------------------------


def test_load_namespace_marks_loaded_and_returns_specs() -> None:
    session = _session()
    session.update_turn(_tools(), _namespaces())
    payload = session.load_namespace("browser")
    assert payload["namespace"] == "browser"
    assert [t["function"]["name"] for t in payload["tools"]] == ["b_one", "b_two"]
    assert session.loaded_namespaces == frozenset({"browser"})


def test_loaded_namespace_injects_from_next_render() -> None:
    session = _session()
    session.update_turn(_tools(), _namespaces())
    session.load_namespace("browser")
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search", "b_one", "b_two"]
    # browser no longer needs a catalog line; core still does.
    assert "browser" not in catalog
    assert "core" in catalog


def test_load_namespace_is_idempotent() -> None:
    session = _session()
    session.update_turn(_tools(), _namespaces())
    first = session.load_namespace("browser")
    second = session.load_namespace("browser")
    assert first == second
    assert session.loaded_namespaces == frozenset({"browser"})


def test_load_unknown_namespace_raises_with_known_list() -> None:
    session = _session()
    session.update_turn(_tools(), _namespaces())
    try:
        session.load_namespace("nope")
    except KeyError as exc:
        message = str(exc)
        assert "nope" in message
        assert "browser" in message
        assert "core" in message
    else:
        raise AssertionError("expected KeyError")


def test_loaded_set_survives_turn_updates() -> None:
    """Dispatch runs every turn — the loaded set must not be rebuilt."""
    session = _session()
    session.update_turn(_tools(), _namespaces())
    session.load_namespace("browser")
    # Next turn: same tools, fresh update.
    session.update_turn(_tools(), _namespaces())
    assert session.loaded_namespaces == frozenset({"browser"})
    wire, _ = session.render_turn()
    assert "b_one" in _wire_names(wire)


# --- policy variations ------------------------------------------------------


def test_disabled_policy_renders_full_legacy_projection() -> None:
    session = _session(enabled=False)
    tools = _tools()
    session.update_turn(tools, _namespaces())
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == [t.name for t in tools]
    assert catalog == ""


def test_custom_eager_namespace() -> None:
    session = _session(eager_namespaces=frozenset({"tool_search", "core"}))
    session.update_turn(_tools(), _namespaces())
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search", "core_a"]
    assert "browser" in catalog
    assert "core" not in catalog


def test_namespace_description_override_used_in_catalog() -> None:
    session = _session(namespace_descriptions={"browser": "Web browsing."})
    session.update_turn(_tools(), _namespaces())
    _, catalog = session.render_turn()
    assert "Web browsing." in catalog


def test_render_without_turn_view_returns_empty() -> None:
    session = _session()
    wire, catalog = session.render_turn()
    assert wire == ()
    assert catalog == ""


def test_unknown_tool_gets_own_namespace() -> None:
    session = _session()
    session.update_turn((FakeTool("mystery"),), {})
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == []
    assert "mystery" in catalog


# --- ContextVar seam --------------------------------------------------------


def test_contextvar_default_none_set_reset() -> None:
    assert current_defer_session() is None
    session = _session()
    token = set_current_defer_session(session)
    try:
        assert current_defer_session() is session
    finally:
        reset_current_defer_session(token)
    assert current_defer_session() is None
