"""ADR-0268 §4 结构保证测试：lca.nothing_to_do 只在 handoff 轮可用。

用户轮 wire 不暴露该工具；模型在用户轮发出该调用时，wire gate 回注
错误（ADR-0268 §14.1、§14.2）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.cognition.body.tools.tool_wire_gate import unexposed_tool_block_observation
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.policy import DEFAULT_NAMESPACE_DESCRIPTIONS, DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.infrastructure.tools.lca import (
    IDENTIFIER,
    NothingToDoTool,
    build_tools,
    filter_handoff_only_tools,
)


class _FakeTool:
    name: ClassVar[str] = "readFile"
    namespace: ClassVar[str] = "file"
    description: ClassVar[str] = "fake file tool"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
    }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


def _decision(*tool_names: str) -> Decision:
    calls = [
        ToolCall(call_id=f"call-{i}", tool_name=name, arguments={})
        for i, name in enumerate(tool_names)
    ]
    return Decision(
        decision_id="dec-1",
        action_type=ActionType.USE_TOOL.value,
        rationale="r",
        confidence=1.0,
        tool_calls=calls,
    )


def test_nothing_to_do_tool_protocol_and_namespace() -> None:
    tool = NothingToDoTool()
    assert isinstance(tool, Tool)
    assert tool.name == IDENTIFIER
    assert tool.namespace == "lca"
    assert tool.parameters == {"type": "object", "properties": {}, "required": []}


def test_default_policy_includes_lca_and_cron() -> None:
    policy = DeferPolicy.default()
    assert "lca" in policy.known_namespaces
    assert "cron" in policy.known_namespaces
    assert policy.namespace_descriptions["lca"]
    assert policy.namespace_descriptions["cron"]


def test_filter_removes_on_user_round() -> None:
    tools: tuple[Tool, ...] = (NothingToDoTool(), _FakeTool())  # type: ignore[arg-type]
    out = filter_handoff_only_tools(tools, "user")
    assert [t.name for t in out] == ["readFile"]


def test_filter_keeps_on_handoff_round() -> None:
    tools: tuple[Tool, ...] = (NothingToDoTool(), _FakeTool())  # type: ignore[arg-type]
    out = filter_handoff_only_tools(tools, "handoff")
    assert [t.name for t in out] == ["lca.nothing_to_do", "readFile"]


def test_build_tools_returns_nothing_to_do() -> None:
    tools = build_tools()
    assert [t.name for t in tools] == [IDENTIFIER]


def test_user_round_call_to_nothing_to_do_is_blocked() -> None:
    """用户轮 wire 不含 lca.nothing_to_do：调用被 wire gate 拒绝并回注错误。"""
    descriptions = dict(DEFAULT_NAMESPACE_DESCRIPTIONS)
    session = ToolDeferSession(DeferPolicy(namespace_descriptions=descriptions))
    # 用户轮工具集：只有 file 域工具，没有 lca.nothing_to_do。
    session.update_turn((_FakeTool(),))
    token = set_current_defer_session(session)
    try:
        obs = unexposed_tool_block_observation(_decision(IDENTIFIER))
        assert obs is not None
        assert obs.success is False
        assert IDENTIFIER in obs.error
        assert "tool_search" in obs.error
        assert obs.extra["tool_wire_reason"] == "namespace_not_loaded"
    finally:
        reset_current_defer_session(token)
