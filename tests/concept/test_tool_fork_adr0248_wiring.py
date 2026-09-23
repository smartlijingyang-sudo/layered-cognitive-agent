"""ADR-0248 运行时总装 — tool.fork.dispatch 接线测试。

验证：
1. gated 模式自动追加 ``send_message`` 声带工具；
2. 子代理（origin="subagent"）物理禁声，绝不带 ``send_message``；
3. ``auto_review_mode != "off"`` 时工具被 ``AutoReviewWrappedTool`` 包装，
   危险命令在 execute 前被硬闸拦截；
4. off / direct / user 默认路径零侵入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.auto_review.models import AutoReviewMode
from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.auto_review.gate import AutoReviewGate
from lca.infrastructure.auto_review.wrapped_tool import AutoReviewWrappedTool
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool_adapter import SendMessageVocalTool
from lca.nodes.concept.tool_fork.dispatch import ToolForkDispatchExecutor


@dataclass
class _ToolStub:
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None
    is_idempotent: bool = True
    effect_kind: str = "ephemeral"
    default_timeout_s: int = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        return Observation(
            observation_id=f"obs_{self.name}",
            success=True,
            payload={"command": args.get("command")},
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        return None


@dataclass
class _ToolsServiceStub:
    tools: dict[str, _ToolStub]

    def fork_for_run(self, bindings: BindingsView) -> _ToolsServiceStub:
        return _ToolsServiceStub(tools=dict(self.tools))

    def list_tools(self) -> list[_ToolStub]:
        return list(self.tools.values())


def _ctx() -> NodeContext:
    return NodeContext(runtime=object(), budget={}, metadata={})


def _input(bindings: BindingsView, tools: _ToolsServiceStub) -> NodeInput:
    return NodeInput(port_values={"bindings": bindings, "tools": tools})


def _bindings(**overrides: Any) -> BindingsView:
    values: dict[str, Any] = {"mode": "team"}
    values.update(overrides)
    return BindingsView(**values)


def _base_tools() -> _ToolsServiceStub:
    return _ToolsServiceStub(
        tools={
            "read_file": _ToolStub(name="read_file"),
            "run_shell": _ToolStub(name="run_shell"),
        }
    )


@pytest.mark.asyncio
async def test_gated_mode_appends_send_message_tool() -> None:
    gate = GatedVocalGate("op_gated")
    bindings = _bindings(vocal_mode="gated", vocal_gate=gate)
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "send_message" in names
    send_tool = next(
        t for t in result.port_values["forked_tools"].items if t.name == "send_message"
    )
    assert isinstance(send_tool, SendMessageVocalTool)


@pytest.mark.asyncio
async def test_direct_mode_does_not_append_send_message() -> None:
    bindings = _bindings(vocal_mode="direct")
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "send_message" not in names


@pytest.mark.asyncio
async def test_subagent_origin_strips_send_message_even_when_gated() -> None:
    tools = _ToolsServiceStub(
        tools={
            "read_file": _ToolStub(name="read_file"),
            "send_message": _ToolStub(name="send_message"),
        }
    )
    gate = GatedVocalGate("op_sub")
    bindings = _bindings(vocal_mode="gated", vocal_gate=gate, origin="subagent")
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, tools))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "send_message" not in names
    assert "read_file" in names


@pytest.mark.asyncio
async def test_auto_review_enforce_wraps_tools_and_blocks_dangerous() -> None:
    bindings = _bindings(
        auto_review_mode="enforce",
        auto_review_gate=AutoReviewGate(mode=AutoReviewMode.ENFORCE),
    )
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    items = result.port_values["forked_tools"].items
    assert all(isinstance(t, AutoReviewWrappedTool) for t in items)
    shell = next(t for t in items if t.name == "run_shell")
    obs = await shell.execute({"command": "cat /etc/shadow"})
    assert obs.success is False


@pytest.mark.asyncio
async def test_auto_review_off_leaves_tools_unwrapped() -> None:
    bindings = _bindings(auto_review_mode="off")
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    items = result.port_values["forked_tools"].items
    assert not any(isinstance(t, AutoReviewWrappedTool) for t in items)


@pytest.mark.asyncio
async def test_gated_mode_appends_box_tools_consuming_box_accessor(tmp_path) -> None:
    from lca.infrastructure.computer.box_accessor import BoxAccessor

    box = BoxAccessor(root_dir=tmp_path / "box")
    gate = GatedVocalGate("op_box")
    bindings = _bindings(vocal_mode="gated", vocal_gate=gate, box_accessor=box)
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "box_read_file" in names
    assert "box_write_file" in names
    assert "box_list_files" in names
    # 默认 auto_review=off：员工机 Shell 不暴露
    assert "box_run_command" not in names
    # 人闸挂载
    assert "request_box_help" in names

    # BoxAccessor 被真实消费：写读闭环
    box_tool = next(
        t for t in result.port_values["forked_tools"].items if t.name == "box_write_file"
    )
    obs = await box_tool.execute({"path": "hello.txt", "content": "hi"})
    assert obs.success is True
    read_tool = next(
        t for t in result.port_values["forked_tools"].items if t.name == "box_read_file"
    )
    read_obs = await read_tool.execute({"path": "hello.txt"})
    assert read_obs.payload["content"] == "hi"


@pytest.mark.asyncio
async def test_gated_mode_exposes_box_shell_only_under_auto_review(tmp_path) -> None:
    from lca.infrastructure.auto_review.gate import AutoReviewGate
    from lca.infrastructure.computer.box_accessor import BoxAccessor

    box = BoxAccessor(root_dir=tmp_path / "box")
    gate = GatedVocalGate("op_box_shell")
    bindings = _bindings(
        vocal_mode="gated",
        vocal_gate=gate,
        box_accessor=box,
        auto_review_mode="enforce",
        auto_review_gate=AutoReviewGate(mode=AutoReviewMode.ENFORCE),
    )
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "box_run_command" in names
    # 工具被 AutoReview 包装，危险命令在 execute 前被拦截
    shell = next(t for t in result.port_values["forked_tools"].items if t.name == "box_run_command")
    assert isinstance(shell, AutoReviewWrappedTool)
    obs = await shell.execute({"command": "cat /etc/shadow"})
    assert obs.success is False


@pytest.mark.asyncio
async def test_gated_subagent_gets_box_files_but_no_help_tool(tmp_path) -> None:
    from lca.infrastructure.computer.box_accessor import BoxAccessor

    box = BoxAccessor(root_dir=tmp_path / "box")
    gate = GatedVocalGate("op_sub_box")
    bindings = _bindings(vocal_mode="gated", vocal_gate=gate, box_accessor=box, origin="subagent")
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, _base_tools()))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert "box_read_file" in names
    assert "request_box_help" not in names
    assert "send_message" not in names


@pytest.mark.asyncio
async def test_gated_mode_orders_tools_by_work_surface_ladder(tmp_path) -> None:
    from lca.infrastructure.computer.box_accessor import BoxAccessor

    tools = _ToolsServiceStub(
        tools={
            "askUserQuestion": _ToolStub(name="askUserQuestion"),
            "web_search": _ToolStub(name="web_search"),
            "run_shell": _ToolStub(name="run_shell"),
            "memory_add": _ToolStub(name="memory_add"),
        }
    )
    box = BoxAccessor(root_dir=tmp_path / "box")
    gate = GatedVocalGate("op_ladder")
    bindings = _bindings(vocal_mode="gated", vocal_gate=gate, box_accessor=box)
    result = await ToolForkDispatchExecutor().node_execute(_ctx(), _input(bindings, tools))
    names = [getattr(t, "name", "") for t in result.port_values["forked_tools"].items]
    assert names.index("memory_add") < names.index("run_shell")
    assert names.index("run_shell") < names.index("web_search")
    assert names.index("web_search") < names.index("askUserQuestion")
    assert names.index("askUserQuestion") < names.index("send_message")
