"""ADR-0256 §7:wire gate 按 namespace 判可见性.

C1-C4 可直接运行:未加载域调用被拒(错误抛回模型重试,不杀 run);
已加载/eager 域放行.
F2 可直接运行:截断参数值被拒(关联在研 _TRUNCATED_VALUE 改动).
F3 以 skip 锁定待实现的重复发射去重.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.body.tools.tool_wire_gate import unexposed_tool_block_observation
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    reset_current_defer_session,
    set_current_defer_session,
)


@dataclass
class FakeTool:
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.description = self.description or f"fake tool {self.name}"
        self.parameters = self.parameters or {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}


DESCRIPTIONS = {
    "tool_search": "推理原语:按需加载工具目录",
    "file": "文件系统:列出、读取、写入、编辑、移动、搜索文件内容",
    "memory": "搜索与写入长期记忆",
}


@pytest.fixture
def defer_session() -> Any:
    session = ToolDeferSession(DeferPolicy(namespace_descriptions=DESCRIPTIONS))
    tools = (FakeTool("tool_search"), FakeTool("readFile"), FakeTool("memory_search"))
    mapping = {"tool_search": "tool_search", "readFile": "file", "memory_search": "memory"}
    session.update_turn(tools, mapping)
    token = set_current_defer_session(session)
    yield session
    reset_current_defer_session(token)


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


def test_c1_call_to_unloaded_namespace_is_blocked(defer_session: Any):
    """未加载域的工具被拒:错误含 tool_search 指引,run 不死(验收 4)."""
    obs = unexposed_tool_block_observation(_decision("memory_search"))
    assert obs is not None
    assert obs.success is False
    assert "tool_search" in obs.error
    assert "memory" in obs.error
    assert "namespace_not_loaded" in str(obs.extra)


def test_c2_call_to_loaded_namespace_passes(defer_session: Any):
    defer_session.load_namespace("file")
    assert unexposed_tool_block_observation(_decision("readFile")) is None


def test_c3_eager_namespace_needs_no_load(defer_session: Any):
    """tool_search 是 eager 域,首 turn 直接调用不被拒."""
    assert unexposed_tool_block_observation(_decision("tool_search")) is None


def test_c4_blocked_call_can_retry_after_load(defer_session: Any):
    """被拒 -> tool_search 加载 -> 重试成功:fail 的是这次调用,不是整个 run.

    回归 run_747963254987:无名 tool call 直接杀死了整个 run.
    """
    decision = _decision("memory_search")
    blocked = unexposed_tool_block_observation(decision)
    assert blocked is not None and blocked.success is False
    # 模型按指引加载后重试,同一 decision 放行,run 继续.
    defer_session.load_namespace("memory")
    assert unexposed_tool_block_observation(decision) is None
    assert "memory" in defer_session.loaded_namespaces


def test_f2_truncated_argument_value_is_rejected():
    """参数值含 4+ 个点或省略号 -> 不是一次调用,直接拒掉(关联在研改动).

    回归 run_56ee6564e3ea:截断的 find 命令被执行了 4 次.
    """
    from lca.cognition.brain.prompt.leaked_tool_call import _call

    assert _call("runCommand", {"command": "find /home......"}) is None
    assert _call("runCommand", {"command": "echo …done"}) is None
    # 合法值不受影响:Python 省略号 ... 恰好 3 个点,放行.
    assert _call("runCommand", {"command": "echo ..."}) is not None
    assert _call("runCommand", {"command": "find /home/lichao"}) is not None


def test_f3_duplicate_emissions_in_one_turn_deduplicated():
    """同一 turn 发射 21 次相同调用,只保留第 1 个良构的.

    回归 run_56ee6564e3ea:同一 find 发射 21 次/turn.
    去重发生在 project_llm_response(_first_of_each_call).
    """
    from lca.cognition.brain.llm_turn.response_projection import project_llm_response
    from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall

    dupes = [
        NativeToolCall(call_id=f"call-{i}", name="listFiles",
                       arguments={"path": "/home/lichao"})
        for i in range(21)
    ]
    other = NativeToolCall(call_id="call-x", name="listFiles",
                           arguments={"path": "/tmp"})
    projection = project_llm_response(LLMResponse(text="", tool_calls=dupes + [other]))
    names = [(c.tool_name, c.arguments.get("path")) for c in projection.tool_calls]
    assert names == [("listFiles", "/home/lichao"), ("listFiles", "/tmp")]
