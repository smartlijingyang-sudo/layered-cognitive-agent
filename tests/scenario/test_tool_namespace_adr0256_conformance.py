"""ADR-0256 全量符合性集成验收测试套件 (INV-01 ~ INV-07).

验证工具命名空间划分规范（ADR-0256 8 域 + ADR-0268 新增 ``lca``/``cron``）：
1. INV-01: 首 turn 目录行严格 9 行纯净描述，绝无 'N tools:' 降级文本；
2. INV-02: 缺少或非法 namespace 的工具在 update_turn 时必抛 ValueError (Fail-fast)；
3. INV-03: 单域加载 tool_search(namespace='file') 一次返回该域全部工具；
4. INV-04: 批量加载 tool_search(namespaces=['file', 'memory']) 支持多域合并去重；
5. INV-05: Wire Gate 对未加载域工具调用直接拦截并返回明确 guidance；
6. INV-06: shell 域工具调用必然触发 REQUIRE_APPROVAL 审批要求；
7. INV-07: 全局消除所有驼峰双拼兼容函数（_name_forms 彻底删除）。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.cognition.body.tools.tool_wire_gate import unexposed_tool_block_observation
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.approval import ApprovalReasonKind
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols import Tool
from lca.infrastructure.runtime_plane.access.approval_engine import (
    NamespaceApprovalStrategy,
    build_default_approval_engine,
)
from lca.infrastructure.tool_defer.policy import (
    DEFAULT_NAMESPACE_DESCRIPTIONS,
    STANDARD_NAMESPACES,
    DeferPolicy,
)
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.infrastructure.tool_defer.tool_search import ToolSearchTool


class _ConformanceTool:
    def __init__(self, name: str, namespace: str) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"conformance tool {name}"
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {"arg": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "tool": self.name, "args": args}


def _make_standard_domain_tools() -> list[Tool]:
    tools: list[Tool] = [ToolSearchTool()]  # core
    for ns in STANDARD_NAMESPACES:
        if ns == "core":
            continue
        tools.append(_ConformanceTool(f"{ns}_sample_tool", namespace=ns))  # type: ignore[arg-type]
    return tools


def test_inv_01_catalog_has_exact_nine_pure_lines_no_tool_counts() -> None:
    """INV-01: 目录行除 eager core 外恰好 9 行，无 'N tools:' 降级文本."""
    session = ToolDeferSession(DeferPolicy.default())
    tools = _make_standard_domain_tools()
    session.update_turn(tools)
    wire, catalog = session.render_turn()

    # core 域在 wire 上
    wire_names = [spec["function"]["name"] for spec in wire]
    assert "tool_search" in wire_names

    # 目录行严格 9 行
    catalog_lines = [line for line in catalog.splitlines() if line.startswith("- ")]
    assert len(catalog_lines) == 9
    assert "tools:" not in catalog
    assert "- core: " not in catalog

    for ns in STANDARD_NAMESPACES:
        if ns == "core":
            continue
        expected_desc = DEFAULT_NAMESPACE_DESCRIPTIONS[ns]
        assert f"- {ns}: {expected_desc}" in catalog


def test_inv_02_missing_or_undeclared_namespace_handling() -> None:
    """INV-02: 未声明 namespace 的工具 fail-soft 停靠 unknown；声明未知域则抛错.

    6d190d51b 起缺失 namespace 不再杀 run（fail-soft，停靠 ``unknown``）。
    声明了 policy 没有描述的 namespace 仍是 fail-fast（ADR-0256 B2）。
    """
    session = ToolDeferSession(DeferPolicy.default())

    class UnannotatedTool:
        def __init__(self) -> None:
            self.name = "orphan"
            self.description = "orphan tool"
            self.parameters: dict[str, Any] = {}

        async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
            return {}

    # 缺失 namespace：fail-soft 停靠 unknown，不抛错。
    session.update_turn((UnannotatedTool(),))  # type: ignore[arg-type]
    namespaces = {ns.name for ns in session.namespaces}
    assert "unknown" in namespaces

    # 声明了 policy 没有描述的 namespace：仍 fail-fast。
    with pytest.raises(ValueError, match="invalid_namespace"):
        session.update_turn((_ConformanceTool("bad", "invalid_namespace"),))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_inv_03_single_domain_loading() -> None:
    """INV-03: tool_search(namespace='file') 一次返回完整该域工具."""
    session = ToolDeferSession(DeferPolicy.default())
    file_tools = [_ConformanceTool(f"file_op_{i}", namespace="file") for i in range(5)]
    tools: list[Tool] = [ToolSearchTool(), *file_tools]  # type: ignore[list-item]
    session.update_turn(tools)

    token = set_current_defer_session(session)
    try:
        searcher = ToolSearchTool()
        obs = await searcher.execute({"namespace": "file"})
        assert obs.success is True
        assert obs.payload["namespace"] == "file"
        assert len(obs.payload["tools"]) == 5
        assert "file" in session.loaded_namespaces
    finally:
        reset_current_defer_session(token)


@pytest.mark.asyncio
async def test_inv_04_batch_loading_multiple_domains() -> None:
    """INV-04: tool_search(namespaces=['file', 'memory']) 批量合并加载并去重."""
    session = ToolDeferSession(DeferPolicy.default())
    tools: list[Tool] = [
        ToolSearchTool(),
        _ConformanceTool("readFile", namespace="file"),  # type: ignore[list-item]
        _ConformanceTool("memory_search", namespace="memory"),  # type: ignore[list-item]
        _ConformanceTool("web_search", namespace="web"),  # type: ignore[list-item]
    ]
    session.update_turn(tools)

    token = set_current_defer_session(session)
    try:
        searcher = ToolSearchTool()
        obs = await searcher.execute({"namespaces": ["file", "memory", "file"]})
        assert obs.success is True
        assert obs.payload["namespaces"] == ["file", "memory"]
        assert len(obs.payload["tools"]) == 2
        assert session.loaded_namespaces == {"file", "memory"}
    finally:
        reset_current_defer_session(token)


def test_inv_05_unloaded_namespace_wire_gate_blocking() -> None:
    """INV-05: Wire Gate 对未加载域调用直接拦截并返回 guidance."""
    session = ToolDeferSession(DeferPolicy.default())
    tools = _make_standard_domain_tools()
    session.update_turn(tools)

    token = set_current_defer_session(session)
    try:
        decision = Decision(
            decision_id="dec-1",
            action_type=ActionType.USE_TOOL.value,
            rationale="test",
            confidence=1.0,
            tool_calls=[
                ToolCall(
                    tool_name="shell_sample_tool",
                    call_id="c1",
                    arguments={"arg": "test"},
                )
            ],
        )
        block_obs = unexposed_tool_block_observation(decision)
        assert block_obs is not None
        assert block_obs.success is False
        assert "belongs to deferred namespace 'shell'" in (block_obs.error or "")
        assert "Call tool_search for its namespace before using it." in (block_obs.error or "")
    finally:
        reset_current_defer_session(token)


def test_inv_06_shell_domain_triggers_approval() -> None:
    """INV-06: shell 域工具调用必然触发 REQUIRE_APPROVAL 审批要求."""
    strategy = NamespaceApprovalStrategy()
    tool_calls = [
        ToolCall(
            tool_name="runCommand",
            call_id="c1",
            arguments={"command": "rm -rf /"},
        )
    ]
    req = strategy.evaluate(tool_calls)
    assert req is not None
    assert req.required is True
    assert req.reason_kind == ApprovalReasonKind.ELEVATED_COMMAND

    engine = build_default_approval_engine()
    engine_req = engine.evaluate(tool_calls)
    assert engine_req.required is True
    assert engine_req.reason_kind == ApprovalReasonKind.ELEVATED_COMMAND


def test_inv_07_no_name_forms_camel_leakage() -> None:
    """INV-07: 全局消除所有驼峰工具双拼与兼容逻辑，_name_forms 彻底删除."""
    import lca.cognition.body.tools.tool_wire_gate as wire_gate

    assert not hasattr(wire_gate, "_name_forms")
