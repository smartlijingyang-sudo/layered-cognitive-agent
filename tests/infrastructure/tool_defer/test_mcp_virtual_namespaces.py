"""MCP virtual namespaces in the defer system (``mcp_<server>``).

Covers: bridge per-server grouping, session ``_describe`` one-liner,
``resolve_namespace`` alias + suggestions, ``search_catalog`` ranking,
and ``render_turn`` catalog text.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.mcp.types import MCPTool
from lca.infrastructure.mcp.bridge import adapt_mcp_tool_to_lca, mcp_namespace_for
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession


class _FakeMgr:
    async def execute_tool(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError


def _mcp_tool(server: str, name: str, description: str = "") -> MCPTool:
    return MCPTool(
        name=name,
        server_name=server,
        qualified_name=f"mcp__{server}__{name}",
        description=description or f"{name} on {server}",
        input_schema={},
    )


class _FakeTool:
    """Minimal structural Tool for session tests."""

    def __init__(self, name: str, namespace: str = "", description: str = "") -> None:
        self.name = name
        self.namespace = namespace
        self.description = description or f"fake tool {name}"
        self.parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _session_with_mcp() -> ToolDeferSession:
    session = ToolDeferSession(DeferPolicy())
    session.update_turn(
        (
            _FakeTool("tool_search", namespace="core"),
            _FakeTool(
                "mcp__corp__oa_my_tickets",
                namespace="mcp_corp",
                description="查询公司内网 OA 工单列表（只读查询）",
            ),
            _FakeTool(
                "mcp__corp__oa_whoami",
                namespace="mcp_corp",
                description="查询当前企业 OA 登录账号的身份卡片信息",
            ),
            _FakeTool(
                "mcp__exa__web_search_exa",
                namespace="mcp_exa",
                description="Search the web for any topic",
            ),
            _FakeTool("read_file", namespace="file", description="读取文件内容"),
        )
    )
    return session


# --- bridge: per-server grouping -------------------------------------------


def test_mcp_namespace_for() -> None:
    assert mcp_namespace_for("corp") == "mcp_corp"
    assert mcp_namespace_for("exa") == "mcp_exa"
    assert mcp_namespace_for("aws-mcp") == "mcp_aws-mcp"


def test_bridge_groups_tools_by_server() -> None:
    corp_tool = adapt_mcp_tool_to_lca(_FakeMgr(), _mcp_tool("corp", "oa_my_tickets"))
    exa_tool = adapt_mcp_tool_to_lca(_FakeMgr(), _mcp_tool("exa", "web_search_exa"))
    assert corp_tool.namespace == "mcp_corp"
    assert exa_tool.namespace == "mcp_exa"
    assert corp_tool.namespace != exa_tool.namespace


# --- session: _describe ------------------------------------------------------


def test_describe_mcp_virtual_namespace() -> None:
    session = _session_with_mcp()
    line = session._describe("mcp_corp", ["a", "b"])
    assert "corp" in line
    assert "2 个" in line
    assert "按需加载" in line


def test_describe_declared_namespace_still_uses_policy() -> None:
    session = _session_with_mcp()
    assert session._describe("file", ["x"]) == "文件系统：列出、读取、写入、编辑、移动、搜索文件内容"


def test_describe_unknown_non_mcp_still_raises() -> None:
    session = _session_with_mcp()
    with pytest.raises(ValueError):
        session._describe("nope", ["x"])


# --- session: resolve / load -------------------------------------------------


def test_resolve_namespace_exact_and_alias() -> None:
    session = _session_with_mcp()
    assert session.resolve_namespace("mcp_corp") == "mcp_corp"  # exact
    assert session.resolve_namespace("corp") == "mcp_corp"  # server-name alias
    assert session.resolve_namespace("core") == "core"  # declared wins


def test_load_namespace_alias_marks_canonical_loaded() -> None:
    session = _session_with_mcp()
    payload = session.load_namespace("corp")
    assert payload["namespace"] == "mcp_corp"
    assert "mcp_corp" in session.loaded_namespaces
    assert [spec["function"]["name"] for spec in payload["tools"]] == [
        "mcp__corp__oa_my_tickets",
        "mcp__corp__oa_whoami",
    ]


def test_load_namespace_unknown_suggests_close_match() -> None:
    session = _session_with_mcp()
    with pytest.raises(KeyError) as excinfo:
        session.load_namespace("crp")
    message = str(excinfo.value)
    assert "mcp_corp" in message
    assert "corp" in message  # alias rendered


# --- session: search_catalog --------------------------------------------------


def test_search_catalog_ranks_mcp_corp_first_for_oa() -> None:
    session = _session_with_mcp()
    hits = session.search_catalog("OA")
    assert hits, "expected at least one hit for 'OA'"
    first = hits[0]
    assert first["namespace"] == "mcp_corp"
    assert first["source"] == "mcp"
    assert "mcp__corp__oa_my_tickets" in first["matched_tools"]


def test_search_catalog_namespace_name_hit_outranks_tool_hit() -> None:
    session = _session_with_mcp()
    hits = session.search_catalog("corp")
    assert hits[0]["namespace"] == "mcp_corp"  # name hit (rank 0)


def test_search_catalog_empty_query_returns_empty() -> None:
    session = _session_with_mcp()
    assert session.search_catalog("   ") == []
    assert session.search_catalog("zzz-no-such-thing") == []


# --- session: render_turn -----------------------------------------------------


def test_render_turn_catalog_lists_mcp_virtual_namespaces() -> None:
    session = _session_with_mcp()
    _wire, catalog = session.render_turn()
    assert "- mcp_corp: MCP 本地服务「corp」的工具（2 个），按需加载" in catalog
    assert "- mcp_exa: MCP 本地服务「exa」的工具（1 个），按需加载" in catalog


# --- ToolSearchTool: query discovery ------------------------------------------


def _bound_session():
    from lca.infrastructure.tool_defer.session import (
        reset_current_defer_session,
        set_current_defer_session,
    )

    session = _session_with_mcp()
    token = set_current_defer_session(session)
    return session, token, reset_current_defer_session


async def test_tool_search_query_discovers_without_loading() -> None:
    from lca.infrastructure.tool_defer.tool_search import ToolSearchTool

    _session, token, reset = _bound_session()
    try:
        obs = await ToolSearchTool().execute({"query": "OA 审批"})
    finally:
        reset(token)
    assert obs.success
    hits = obs.payload["namespaces"]
    assert hits[0]["namespace"] == "mcp_corp"
    assert hits[0]["source"] == "mcp"


async def test_tool_search_namespace_wins_over_query() -> None:
    from lca.infrastructure.tool_defer.tool_search import ToolSearchTool

    _session, token, reset = _bound_session()
    try:
        obs = await ToolSearchTool().execute({"namespace": "file", "query": "OA"})
    finally:
        reset(token)
    assert obs.success
    assert obs.payload["namespace"] == "file"  # load path, not discovery


async def test_tool_search_query_miss_suggests() -> None:
    from lca.infrastructure.tool_defer.tool_search import ToolSearchTool

    _session, token, reset = _bound_session()
    try:
        obs = await ToolSearchTool().execute({"namespace": "crp"})
    finally:
        reset(token)
    assert not obs.success
    assert "mcp_corp" in (obs.error or "")
