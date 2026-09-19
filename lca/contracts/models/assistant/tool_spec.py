"""``{home}/tools/<tool_id>/tool.json`` 的冻结 schema（ADR-0243 D3）。

自定义工具是声明式定义：name / description / parameters（OpenAI
function-calling schema）/ required_grant / handler。handler 闭集：

- ``builtin_preset`` —— 包装一个内置工具，``args`` 与调用参数合并后执行，
  不新开副作用路径（I-B18）；
- ``sandbox_script`` —— 在 agent 工作区沙箱执行 ``command``（执行缝复用
  ``run_skill_script``，放后期 PR）。

本模块只校验形状（未知字段 fail-closed、frozen 不可变）。``builtin``
是否真实存在、参数 schema 是否合法由运行时/注册表层校验，不在 contracts
内 —— contracts 不得 import 插件实现（AGENTS.md §4）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TOOL_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


class ToolHandlerSpec(BaseModel):
    """自定义工具的执行策略。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    """handler 闭集（ADR-0243 D3）：builtin_preset | sandbox_script。"""

    builtin: str | None = None
    """``builtin_preset``：要包装的内置工具名。"""

    args: dict[str, object] = Field(default_factory=dict)
    """``builtin_preset``：与调用参数合并的固定参数（调用参数优先）。"""

    command: str | None = None
    """``sandbox_script``：要在 agent 工作区执行的 shell 命令。"""

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value not in ("builtin_preset", "sandbox_script"):
            raise ValueError(f"未知 handler.kind: {value}")
        return value

    @field_validator("builtin")
    @classmethod
    def _validate_builtin(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("builtin 必须为非空字符串或 None")
        return value

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("command 必须为非空字符串或 None")
        return value


class ToolSpec(BaseModel):
    """``{home}/tools/<tool_id>/tool.json`` 的完整定义。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    """工具名（``^[a-zA-Z][a-zA-Z0-9_]{0,63}$``），作为 function-calling 的 name。"""

    description: str
    """工具描述，模型可见。"""

    parameters: dict[str, object] = Field(default_factory=dict)
    """OpenAI function-calling 参数 schema（``type: object`` 等）。"""

    required_grant: str = ""
    """可选：执行该工具需要的能力 grant（C5 衰减语义）。"""

    handler: ToolHandlerSpec
    """执行策略（ADR-0243 D3）。"""

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        name = value.strip()
        if not _TOOL_NAME_RE.match(name):
            raise ValueError(
                f"非法工具名 {value!r}: 必须以字母开头，仅含 [a-zA-Z0-9_]，长度 <= 64"
            )
        return name

    @field_validator("required_grant")
    @classmethod
    def _validate_grant(cls, value: str) -> str:
        return value.strip()


__all__ = ["ToolHandlerSpec", "ToolSpec"]
