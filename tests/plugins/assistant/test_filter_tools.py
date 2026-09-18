"""Unit tests for ``filter_tools_by_assistant`` (ADR-0242 D4 / I-B3).

Covers allow/deny/grant semantics, C5 fail-closed decay (malformed
``tools.yaml`` => deny-all), and the missing-``grants.yaml`` narrowing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.plugins.assistant.tools import filter_tools_by_assistant


class _StubTool:
    """Minimal tool shape; only ``name`` / ``required_grant`` are read."""

    def __init__(self, name: str, required_grant: str | None = None) -> None:
        self.name = name
        self.required_grant = required_grant


def _write_tools(home: Path, *, allow: list[str], deny: list[str]) -> None:
    (home / "tools.yaml").write_text(
        f"tools:\n  allow: [{', '.join(allow)}]\n  deny: [{', '.join(deny)}]\n",
        encoding="utf-8",
    )


def _write_grants(home: Path, grants: list[str]) -> None:
    (home / "grants.yaml").write_text(f"grants: [{', '.join(grants)}]\n", encoding="utf-8")


def _tool(name: str, required_grant: str | None = None) -> _StubTool:
    return _StubTool(name, required_grant)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "asst_home"
    home.mkdir()
    return home


class TestFilterToolsByAssistant:
    def test_allow_list_keeps_tools(self, home: Path) -> None:
        _write_tools(home, allow=["alpha", "beta"], deny=[])
        tools = [_tool("alpha"), _tool("beta"), _tool("gamma")]
        result = filter_tools_by_assistant(tools, home)
        assert [t.name for t in result] == ["alpha", "beta"]

    def test_empty_allow_keeps_grant_agnostic_tools(self, home: Path) -> None:
        """``allow: []`` means no name restriction: grant-agnostic tools are
        kept unless denied (default-permit)."""
        _write_tools(home, allow=[], deny=[])
        result = filter_tools_by_assistant([_tool("alpha"), _tool("beta")], home)
        assert [t.name for t in result] == ["alpha", "beta"]

    def test_deny_list_drops_tools(self, home: Path) -> None:
        _write_tools(home, allow=["alpha", "beta"], deny=["alpha"])
        result = filter_tools_by_assistant([_tool("alpha"), _tool("beta")], home)
        assert [t.name for t in result] == ["beta"]

    def test_grant_set_filters_tools_requiring_grants(self, home: Path) -> None:
        _write_tools(home, allow=[], deny=[])
        _write_grants(home, ["workspace.write"])
        tools = [
            _tool("writer", required_grant="workspace.write"),
            _tool("importer", required_grant="skill.import"),
        ]
        result = filter_tools_by_assistant(tools, home)
        assert [t.name for t in result] == ["writer"]

    def test_grant_coverage_comes_only_from_grants_yaml(self, home: Path) -> None:
        """A grant string in ``tools.yaml.allow`` does not cover a tool that
        requires that grant; coverage comes only from ``grants.yaml``."""
        _write_tools(home, allow=["workspace.write"], deny=[])
        result = filter_tools_by_assistant([_tool("writer", "workspace.write")], home)
        assert result == ()


# ── tools_from_scope → filter_tools_by_assistant 集成（I-B3 回归）─────


class _FakeMaterializingTools:
    def __init__(self, tools: list[object]) -> None:
        self._tools = tuple(tools)

    def materialize(self, view: object) -> tuple[object, ...]:
        return self._tools


class _FakeFilterScope:
    """提供 tools_from_scope 所需的 capability seam。"""

    def __init__(self, tools: list[object]) -> None:
        self._tools = _FakeMaterializingTools(tools)

    def require(self, key: str) -> object:
        if key == "tools":
            return self._tools
        if key in {"file_store", "sandbox", "search", "skills"}:
            return object()
        raise KeyError(key)


class TestToolsFromScopeFiltersByAssistant:
    def test_assistant_id_applies_home_filter(self, tmp_path: Path) -> None:
        """带 assistant_id 时，tools_from_scope 返回 Home 过滤后的工具集。"""
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
            tools_from_scope,
        )

        home = tmp_path / "asst_home"
        home.mkdir()
        _write_tools(home, allow=["alpha"], deny=["beta"])
        scope = _FakeFilterScope([_tool("alpha"), _tool("beta"), _tool("gamma")])

        result = tools_from_scope(
            scope,
            None,
            assistant_id="asst_x",
            home_path=str(home),
        )
        assert [t.name for t in result] == ["alpha"]

    def test_no_assistant_id_returns_full_set(self, tmp_path: Path) -> None:
        """I-B8:无 assistant_id 路径返回原始工具集，不做过滤。"""
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
            tools_from_scope,
        )

        scope = _FakeFilterScope([_tool("alpha"), _tool("beta")])
        result = tools_from_scope(scope, None)
        assert [t.name for t in result] == ["alpha", "beta"]

    def test_tool_without_grant_requires_allow_membership(self, home: Path) -> None:
        """A non-empty allow list narrows grant-agnostic tools to the listed
        names instead of widening the set."""
        _write_tools(home, allow=["alpha"], deny=[])
        result = filter_tools_by_assistant([_tool("alpha"), _tool("orphan")], home)
        assert [t.name for t in result] == ["alpha"]

    def test_missing_tools_yaml_denies_all(self, home: Path) -> None:
        result = filter_tools_by_assistant([_tool("alpha")], home)
        assert result == ()

    def test_malformed_tools_yaml_denies_all(self, home: Path) -> None:
        (home / "tools.yaml").write_text("tools:\n  allow: [unclosed\n", encoding="utf-8")
        assert filter_tools_by_assistant([_tool("alpha")], home) == ()

    def test_tools_yaml_wrong_shape_denies_all(self, home: Path) -> None:
        (home / "tools.yaml").write_text("tools: not-a-dict\n", encoding="utf-8")
        assert filter_tools_by_assistant([_tool("alpha")], home) == ()

    def test_missing_grants_yaml_drops_tools_requiring_grants(self, home: Path) -> None:
        _write_tools(home, allow=["alpha"], deny=[])
        tools = [
            _tool("alpha"),
            _tool("writer", required_grant="workspace.write"),
        ]
        result = filter_tools_by_assistant(tools, home)
        assert [t.name for t in result] == ["alpha"]

    def test_malformed_grants_yaml_treated_as_empty(self, home: Path) -> None:
        _write_tools(home, allow=["alpha"], deny=[])
        (home / "grants.yaml").write_text("grants: [unclosed\n", encoding="utf-8")
        result = filter_tools_by_assistant(
            [_tool("alpha"), _tool("writer", required_grant="workspace.write")], home
        )
        assert [t.name for t in result] == ["alpha"]

    def test_deny_wins_over_grant_coverage(self, home: Path) -> None:
        _write_tools(home, allow=[], deny=["writer"])
        _write_grants(home, ["workspace.write"])
        result = filter_tools_by_assistant([_tool("writer", "workspace.write")], home)
        assert result == ()

    def test_returns_empty_tuple_for_empty_tools(self, home: Path) -> None:
        _write_tools(home, allow=["alpha"], deny=[])
        assert filter_tools_by_assistant([], home) == ()
