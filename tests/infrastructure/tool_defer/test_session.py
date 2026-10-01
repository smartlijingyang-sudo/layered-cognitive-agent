"""Tests for ToolDeferSession (lca.infrastructure.tool_defer.session)."""

from __future__ import annotations

import json
from typing import Any

from lca.infrastructure.tool_defer.policy import DEFAULT_NAMESPACE_DESCRIPTIONS, DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    current_defer_session,
    reset_current_defer_session,
    set_current_defer_session,
)


class FakeTool:
    """Minimal structural Tool: name/description/parameters + execute."""

    def __init__(
        self, name: str, params: dict[str, Any] | None = None, namespace: str = ""
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake tool {name}"
        self.parameters = params or {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _tools() -> tuple[FakeTool, ...]:
    return (
        FakeTool("tool_search", namespace="core"),
        FakeTool("core_a", namespace="core"),
        FakeTool("b_one", namespace="web"),
        FakeTool("b_two", namespace="web"),
    )


def _namespaces() -> dict[str, str]:
    return {
        "tool_search": "core",
        "core_a": "core",
        "b_one": "web",
        "b_two": "web",
    }


def _session(**policy_kw: Any) -> ToolDeferSession:
    return ToolDeferSession(DeferPolicy(**policy_kw))


def _wire_names(wire: tuple[dict[str, Any], ...]) -> list[str]:
    return [spec["function"]["name"] for spec in wire]


# --- render_turn: first-turn projection ------------------------------------


def test_missing_loader_does_not_hide_every_tool() -> None:
    """Defer without tool_search is a deadlock. Render the full list instead."""
    session = _session()
    tools = (FakeTool("runCommand", namespace="shell"), FakeTool("readFile", namespace="file"))
    session.update_turn(tools)
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["runCommand", "readFile"]
    assert catalog == ""


def test_first_turn_injects_only_eager_schemas() -> None:
    session = _session()
    session.update_turn(_tools())
    wire, catalog = session.render_turn()
    # core is the eager namespace; tool_search and core_a are both in it.
    assert _wire_names(wire) == ["tool_search", "core_a"]
    assert "web" in catalog
    assert "core" not in catalog


def test_unloaded_namespace_schemas_never_leak_into_catalog() -> None:
    """Audit: full parameters of unloaded namespaces must not appear in
    the catalog text — otherwise the token saving is an illusion."""
    session = _session()
    tools = _tools()
    session.update_turn(tools)
    _, catalog = session.render_turn()
    for tool in tools:
        if tool.name != "tool_search":
            assert json.dumps(tool.parameters) not in catalog
    # No per-tool schema fragment at all — only one-liners.
    assert '"properties"' not in catalog


def test_catalog_hint_appears_only_once_at_the_end() -> None:
    """Each deferred namespace line carries just its name and description.

    The loading hint lives only in the trailing ``discovery_rule``, not on
    every line, so a 64-namespace catalog does not repeat it 64 times.
    """
    session = _session()
    session.update_turn(_tools())
    _, catalog = session.render_turn()
    # discovery_rule 里只有一次 loading hint；每行目录不再重复它
    assert catalog.count("via tool_search") == 1
    assert catalog.count("[deferred —") == 0
    assert catalog.count("- web: 联网搜索与网页抓取") == 1
    # core is the eager namespace; tool_search and core_a both there, so no catalog line for core
    assert "core" not in catalog


def test_deferred_wire_is_smaller_than_full_wire() -> None:
    session = _session()
    tools = _tools()
    session.update_turn(tools)
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
    session.update_turn(_tools())
    payload = session.load_namespace("web")
    assert payload["namespace"] == "web"
    assert [t["function"]["name"] for t in payload["tools"]] == ["b_one", "b_two"]
    assert session.loaded_namespaces == frozenset({"web"})


def test_loaded_namespace_injects_from_next_render() -> None:
    session = _session()
    session.update_turn(_tools())
    session.load_namespace("web")
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search", "core_a", "b_one", "b_two"]
    # web no longer needs a catalog line; core is eager so not in catalog either.
    assert "web" not in catalog
    assert "core" not in catalog


def test_load_namespace_is_idempotent() -> None:
    session = _session()
    session.update_turn(_tools())
    first = session.load_namespace("web")
    second = session.load_namespace("web")
    assert first == second
    assert session.loaded_namespaces == frozenset({"web"})


def test_load_unknown_namespace_raises_with_known_list() -> None:
    session = _session()
    session.update_turn(_tools())
    try:
        session.load_namespace("nope")
    except KeyError as exc:
        message = str(exc)
        assert "nope" in message
        assert "web" in message
        assert "core" in message
    else:
        raise AssertionError("expected KeyError")


def test_loaded_set_survives_turn_updates() -> None:
    """Dispatch runs every turn — the loaded set must not be rebuilt."""
    session = _session()
    session.update_turn(_tools())
    session.load_namespace("web")
    # Next turn: same tools, fresh update.
    session.update_turn(_tools())
    assert session.loaded_namespaces == frozenset({"web"})
    wire, _ = session.render_turn()
    assert "b_one" in _wire_names(wire)


# --- policy variations ------------------------------------------------------


def test_disabled_policy_renders_full_legacy_projection() -> None:
    session = _session(enabled=False)
    tools = _tools()
    session.update_turn(tools)
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == [t.name for t in tools]
    assert catalog == ""


def test_custom_eager_namespace() -> None:
    # Add "web" as an additional eager namespace on top of the default "core".
    session = _session(eager_namespaces=frozenset({"core", "web"}))
    session.update_turn(_tools())
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search", "core_a", "b_one", "b_two"]
    assert "web" not in catalog
    assert "core" not in catalog


def test_namespace_description_override_used_in_catalog() -> None:
    descriptions = {**DEFAULT_NAMESPACE_DESCRIPTIONS, "web": "Web browsing."}
    session = _session(namespace_descriptions=descriptions)
    session.update_turn(_tools())
    _, catalog = session.render_turn()
    assert "Web browsing." in catalog


def test_render_without_turn_view_returns_empty() -> None:
    session = _session()
    wire, catalog = session.render_turn()
    assert wire == ()
    assert catalog == ""


def test_turn_without_the_loader_renders_every_schema() -> None:
    """No tool_search on the turn. Hiding mystery and pointing at a missing loader deadlocks."""
    session = _session()
    session.update_turn((FakeTool("mystery", namespace="file"),))
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["mystery"]
    assert catalog == ""


def test_unknown_tool_stays_deferred_when_the_loader_is_present() -> None:
    session = _session()
    session.update_turn(
        (FakeTool("tool_search", namespace="core"), FakeTool("mystery", namespace="file")),
    )
    wire, catalog = session.render_turn()
    assert _wire_names(wire) == ["tool_search"]
    assert "file" in catalog


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
