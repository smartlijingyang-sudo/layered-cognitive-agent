"""AssistantCustomTool tests（ADR-0243 D5）。

覆盖：

- builtin_preset：固定 args 与调用参数合并后交给内置工具执行
- 内置工具不可解析 ⇒ 明确失败
- validate：按 parameters.required 做前置校验
- sandbox_script handler 本期返回明确不支持
"""

from __future__ import annotations

import pytest

from lca.contracts.models.assistant.tool_spec import ToolHandlerSpec, ToolSpec
from lca.contracts.models.core.execution.decision import Observation
from lca.infrastructure.tools.assistant.custom_tool import AssistantCustomTool


class _FakeBuiltin:
    name = "runCommand"

    def __init__(self) -> None:
        self.last_args: dict[str, object] | None = None

    async def execute(self, args: dict[str, object]) -> Observation:
        self.last_args = args
        return Observation(observation_id="obs_run", success=True, payload={"ran": args})


def _spec(**overrides: object) -> ToolSpec:
    base = ToolSpec(
        name="my_tool",
        description="包装 runCommand",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=ToolHandlerSpec(
            kind="builtin_preset", builtin="runCommand", args={"command": "ls"}
        ),
    )
    return base.model_copy(update=overrides)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_builtin_preset_merges_preset_and_call_args() -> None:
    builtin = _FakeBuiltin()
    tool = AssistantCustomTool(_spec(), builtin_resolver=lambda name: builtin if name == "runCommand" else None)
    result = await tool.execute({"path": "/tmp"})  # noqa: S108 - test fixture
    assert result.success is True
    assert builtin.last_args == {"command": "ls", "path": "/tmp"}  # noqa: S108 - test fixture


@pytest.mark.asyncio
async def test_builtin_preset_missing_builtin_fails() -> None:
    tool = AssistantCustomTool(_spec(), builtin_resolver=lambda name: None)
    result = await tool.execute({})
    assert result.success is False
    assert "不可用" in (result.error or "")


@pytest.mark.asyncio
async def test_validate_required_params() -> None:
    spec = _spec()
    spec = spec.model_copy(
        update={
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            }
        }
    )  # type: ignore[arg-type]
    builtin = _FakeBuiltin()
    tool = AssistantCustomTool(spec, builtin_resolver=lambda name: builtin)
    assert tool.validate({}) is not None
    assert tool.validate({"path": "/x"}) is None


@pytest.mark.asyncio
async def test_sandbox_script_handler_unsupported() -> None:
    spec = ToolSpec(
        name="s_tool",
        description="sandbox",
        handler=ToolHandlerSpec(kind="sandbox_script", command="echo hi"),
    )
    tool = AssistantCustomTool(spec, builtin_resolver=lambda name: None)
    result = await tool.execute({})
    assert result.success is False
    assert "尚未支持" in (result.error or "")
