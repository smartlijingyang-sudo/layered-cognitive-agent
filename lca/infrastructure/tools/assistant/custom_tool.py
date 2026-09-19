"""Assistant custom tool —— ``{home}/tools/<tool_id>/tool.json`` 的运行时实现（ADR-0243 D5）。

``ToolSpec.handler.kind`` 闭集：

- ``builtin_preset`` —— 包装一个内置工具：固定 ``args`` 与调用参数合并后
  交给内置工具执行。不新开副作用路径（I-B18）；内置工具不可解析时该工具
  在 fork 阶段被跳过。
- ``sandbox_script`` —— 在 agent 工作区沙箱执行 shell 命令。执行缝复用
  ``run_skill_script``，放后期 PR；本期构造时若遇到返回明确不支持。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.assistant.tool_spec import ToolSpec
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool

_BUILTIN_PRESET = "builtin_preset"
_SANDBOX_SCRIPT = "sandbox_script"


class AssistantCustomTool:
    """一个 ``ToolSpec`` 的运行时实例（不显式继承 ``Tool`` 协议）。

    ``name`` / ``description`` / ``parameters`` 是实例属性（来自
    ``tool.json``），``ToolSchema.from_any`` 经 ``getattr`` 读取，兼容
    LLM 边界序列化；``is_idempotent`` / ``effect_kind`` /
    ``default_timeout_s`` 以实例属性满足 ``Tool`` 协议形状。
    """

    def __init__(
        self,
        spec: ToolSpec,
        *,
        builtin_resolver: Callable[[str], Tool | None],
    ) -> None:
        self._spec = spec
        self._builtin_resolver = builtin_resolver
        self.name: str = spec.name
        self.description: str = spec.description
        self.parameters: dict[str, Any] = spec.parameters
        self.is_idempotent: bool = False
        self.effect_kind: str = "ephemeral"
        self.default_timeout_s: int = DEFAULT_TOOL_TIMEOUT_S

    def validate(self, args: dict[str, Any]) -> str | None:
        """按 ``parameters`` 的 ``required`` 列表做前置校验。"""
        required = self._spec.parameters.get("required") if isinstance(self._spec.parameters, dict) else None
        if not isinstance(required, list):
            return None
        for key in required:
            if key not in args or args[key] in (None, ""):
                return f"缺少必填参数: {key}"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)

        handler = self._spec.handler
        if handler.kind == _BUILTIN_PRESET:
            return await self._execute_builtin_preset(handler.builtin or "", handler.args, args, start)
        if handler.kind == _SANDBOX_SCRIPT:
            return self._fail(start, "sandbox_script handler 尚未支持（ADR-0243 后期 PR）")
        return self._fail(start, f"未知 handler.kind: {handler.kind}")

    async def _execute_builtin_preset(
        self,
        builtin_name: str,
        preset_args: dict[str, object],
        call_args: dict[str, Any],
        start: float,
    ) -> Observation:
        builtin = self._builtin_resolver(builtin_name)
        if builtin is None:
            return self._fail(start, f"内置工具 {builtin_name!r} 在该 run 中不可用")
        merged: dict[str, Any] = dict(preset_args)
        merged.update(call_args)
        try:
            return await builtin.execute(merged)
        except Exception as exc:  # pragma: no cover — 内置工具自身失败语义
            return self._fail(start, f"内置工具 {builtin_name!r} 执行失败: {exc}")

    def _fail(self, start: float, message: str) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=message,
            latency_ms=int((time.monotonic() - start) * 1000),
            extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
        )


def custom_tool_from_spec(
    spec: ToolSpec,
    *,
    builtin_resolver: Callable[[str], Tool | None],
) -> AssistantCustomTool:
    """从 ``ToolSpec`` 构造运行时工具。"""
    return AssistantCustomTool(spec, builtin_resolver=builtin_resolver)


def parse_tool_spec_json(text: str) -> ToolSpec:
    """解析并校验 ``tool.json`` 全文。"""
    return ToolSpec.model_validate_json(text)


__all__ = [
    "AssistantCustomTool",
    "custom_tool_from_spec",
    "parse_tool_spec_json",
]
