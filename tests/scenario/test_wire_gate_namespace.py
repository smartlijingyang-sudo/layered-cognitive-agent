"""ADR-0256 §7:wire gate 按 namespace 判可见性.

C1-C4 可直接运行:未加载域调用被拒(错误抛回模型重试,不杀 run);
已加载/eager 域放行.
F2 可直接运行:截断参数值被拒(关联在研 _TRUNCATED_VALUE 改动).
F3 已是真用例:同 turn 重复发射去重（test_f3_duplicate_emissions_in_one_turn_deduplicated）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.body.tools.tool_wire_gate import unexposed_tool_block_observation
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    OBS_RESULT_KIND,
    TOOL_WIRE_INVALID,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession


@dataclass
class FakeTool:
    name: str
    namespace: str = ""
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
    "core": "推理原语:按需加载工具目录",
    "file": "文件系统:列出、读取、写入、编辑、移动、搜索文件内容",
    "memory": "搜索与写入长期记忆",
}


@pytest.fixture
def defer_session() -> Any:
    # RA-144: the gate takes the session explicitly; the fixture no longer
    # publishes the ambient ContextVar.
    session = ToolDeferSession(DeferPolicy(namespace_descriptions=DESCRIPTIONS))
    tools = (
        FakeTool("tool_search", namespace="core"),
        FakeTool("readFile", namespace="file"),
        FakeTool("memory_search", namespace="memory"),
    )
    session.update_turn(tools)
    return session


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
    """未加载域的工具被拒:错误含 tool_search 指引,run 不死(验收 4).

    ``memory`` 自 ADR-0260 起是 eager 域,``memory_search`` 首 turn 就在 wire
    上;这里用仍为 deferred 的 ``file`` 域工具 ``readFile`` 验证拒绝路径。
    """
    obs = unexposed_tool_block_observation(_decision("readFile"), defer_session)
    assert obs is not None
    assert obs.success is False
    assert "tool_search" in obs.error
    assert "file" in obs.error
    assert "namespace_not_loaded" in str(obs.extra)


def test_c2_call_to_loaded_namespace_passes(defer_session: Any):
    defer_session.load_namespace("file")
    assert unexposed_tool_block_observation(_decision("readFile"), defer_session) is None


def test_c3_eager_namespace_needs_no_load(defer_session: Any):
    """tool_search 是 eager 域,首 turn 直接调用不被拒."""
    assert unexposed_tool_block_observation(_decision("tool_search"), defer_session) is None


def test_c4_blocked_call_can_retry_after_load(defer_session: Any):
    """被拒 -> tool_search 加载 -> 重试成功:fail 的是这次调用,不是整个 run.

    回归 run_747963254987:无名 tool call 直接杀死了整个 run.
    """
    decision = _decision("readFile")
    blocked = unexposed_tool_block_observation(decision, defer_session)
    assert blocked is not None and blocked.success is False
    # 模型按指引加载后重试,同一 decision 放行,run 继续.
    defer_session.load_namespace("file")
    assert unexposed_tool_block_observation(decision, defer_session) is None
    assert "file" in defer_session.loaded_namespaces


def test_snake_case_names_the_real_namespace_then_passes_once_loaded():
    """write_file and writeFile are one tool. The unloaded error names file.

    A spelling the registry does not store used to report namespace 'deferred',
    so the retry after tool_search was refused again.
    """
    session = ToolDeferSession(DeferPolicy(namespace_descriptions=DESCRIPTIONS))
    session.update_turn(
        (
            FakeTool("tool_search", namespace="core"),
            FakeTool("writeFile", namespace="file"),
        )
    )
    blocked = unexposed_tool_block_observation(_decision("write_file"), session)
    assert blocked is not None and blocked.success is False
    assert "namespace 'file'" in blocked.error
    assert "namespace 'deferred'" not in blocked.error
    session.load_namespace("file")
    assert unexposed_tool_block_observation(_decision("write_file"), session) is None


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
        NativeToolCall(call_id=f"call-{i}", name="listFiles", arguments={"path": "/home/lichao"})
        for i in range(21)
    ]
    other = NativeToolCall(call_id="call-x", name="listFiles", arguments={"path": "/var/data"})
    projection = project_llm_response(LLMResponse(text="", tool_calls=[*dupes, other]))
    names = [(c.tool_name, c.arguments.get("path")) for c in projection.tool_calls]
    assert names == [("listFiles", "/home/lichao"), ("listFiles", "/var/data")]
def test_ra143_unexposed_block_uses_shared_extra_contract(defer_session: Any):
    """RA-143: the unexposed gate builds through _wire_block_observation.

    The blocked-Observation `extra` key set must match the single
    constructor seam's contract; the model-facing text keeps the
    tool_search instruction and the namespace name.
    """
    obs = unexposed_tool_block_observation(_decision("readFile"), defer_session)
    assert obs is not None
    assert obs.success is False
    assert set(obs.extra or {}) == {
        FAILURE_KIND,
        OBS_RESULT_KIND,
        TOOL_WIRE_STATUS,
        TOOL_WIRE_REASON,
    }
    assert obs.extra[TOOL_WIRE_STATUS] == TOOL_WIRE_INVALID
    assert obs.extra[TOOL_WIRE_REASON] == "namespace_not_loaded"
    assert "tool_search" in (obs.error or "")
    assert "file" in (obs.error or "")
