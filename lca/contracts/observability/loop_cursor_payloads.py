"""ADR-0169 D4:LoopCursor record_* 方法的 payload frozen dataclass。

强类型契约(SSOT 收口):
- step_id 与 incarnation 不让业务路径填(由 cursor 注入,见 PR-7)
- system / tools / messages / manifest digest + path 由 ModelVisibleCapture 写(PR-12)
- tools schema 由 ``ToolSchema`` 强类型 dataclass 表达(避免 record_tools 接 ``Any``
  在 LLM adapter 边界丢 OpenAI-style schema 字段)
- ``phase.<x>.fold`` EP payload 由 ``PhaseFoldPayload`` 强类型表达,杜绝历史 bug
  (LLM adapter 把 ``model=`` 误传成 ``objective=``,spine 同 EP 出现两条 payload)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ThinkingRecord:
    content_digest: str
    content_path: str | None
    token_count: int | None
    thinking_kind: Literal["reasoning", "final_response", "compaction"]


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    args_digest: str
    args_payload_path: str | None
    call_seq: int  # cursor 内自增


@dataclass(frozen=True)
class ToolResultRecord:
    tool_name: str
    result_digest: str
    result_path: str | None
    outcome: Literal["ok", "failure", "timeout", "denied"]


@dataclass(frozen=True)
class RequestHeader:
    """cursor 注入 step_id / incarnation;业务路径不能填(ADR-0169 D4)。"""

    step_id: str
    incarnation: int
    reason: Literal["initial", "next_step", "series", "change", "inherited"]
    model: str
    system_digest: str
    system_path: str
    tools_digest: str
    tools_path: str
    messages_digest: str
    messages_path: str
    manifest_digest: str
    manifest_path: str
    inherited_from_step: str | None = None


@dataclass(frozen=True)
class ToolSchema:
    """工具 schema 强类型表达 —— 单一权威形态。

    LLM adapter 边界用 ``ToolSchema.from_openai(...)`` / ``from_any(...)`` 把
    异源对象规整成此形态,然后再传给 record_tools / ModelVisibleCapture。
    避免 ``tuple[Any, ...]`` 序列化路径里丢字段(历史 bug:17/22 个 schema
    落盘成空 dict,因为 ``vars()`` 抓不到 dataclass 字段之外的属性)。
    """

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    # 内部句柄在 LLM 边界被剥掉;只保留公开 OpenAI 风格字段。`_extras`
    # 仅供 trace 调试,不入 digest。
    _extras: dict[str, Any] = field(default_factory=dict)

    def to_openai_dict(self) -> dict[str, Any]:
        """导出 OpenAI function-calling 风格 schema dict(供 capture 落盘)。"""
        d: dict[str, Any] = {"type": "function", "function": {"name": self.name}}
        fn = d["function"]
        # 用 ``is not None`` 而非 truthy,保留显式空字符串 description —— 与 OpenAI SDK 行为一致。
        if self.description is not None:
            fn["description"] = self.description
        if self.parameters is not None:
            fn["parameters"] = self.parameters
        return d

    @staticmethod
    def from_openai(schema: dict[str, Any]) -> ToolSchema:
        """从 OpenAI 风格 dict 反向构造。"""
        fn = schema.get("function", schema) if isinstance(schema, dict) else {}
        return ToolSchema(
            name=str(fn.get("name", "")),
            description=str(fn.get("description", "")),
            parameters=dict(fn.get("parameters") or {}),
        )

    @staticmethod
    def from_any(obj: Any) -> ToolSchema:
        """边界 transform —— 把异源 tool 对象归一到 ``ToolSchema``。

        优先级:
        1. ``obj.to_openai_dict()``(LLM provider SDK 风格)
        2. OpenAI 风格 dict
        3. ``obj.name`` / ``obj.description`` / ``obj.parameters`` 属性
        4. 兜底:name=str(obj);description 与 parameters 空,留 trace hint
        """
        if obj is None:
            return ToolSchema(name="<unknown>")
        to_openai = getattr(obj, "to_openai_dict", None)
        if callable(to_openai):
            try:
                return ToolSchema.from_openai(to_openai())
            except Exception:  # noqa: S110 — 兜底走下一条 transform 分支
                pass
        if isinstance(obj, dict):
            return ToolSchema.from_openai(obj)
        name = getattr(obj, "name", None) or getattr(obj, "__name__", None) or str(obj)
        description = getattr(obj, "description", "") or ""
        parameters = getattr(obj, "parameters", None) or {}
        extras: dict[str, Any] = {}
        for attr in ("_store", "_importer", "_sandbox", "_file_store"):
            if hasattr(obj, attr):
                extras[attr] = f"<elided:{type(getattr(obj, attr)).__name__}>"
        return ToolSchema(
            name=str(name),
            description=str(description),
            parameters=dict(parameters) if isinstance(parameters, dict) else {},
            _extras=extras,
        )


@dataclass(frozen=True)
class PhaseFoldPayload:
    """``phase.<name>.fold`` EP payload 强类型 —— cursor 唯一写入者(ADR-0169 P2)。

    单一字段来源,杜绝 ``coord.emit_phase`` 双写与 ``objective=model`` keyword 错位
    (历史 bug:spine 同时出现 objective=模型名 与 objective=用户文本 两条同 EP)。
    """

    phase: Literal["perceive", "think", "gate", "act", "reflect", "remember", "stop"]
    # objective 的来源显式化:不再接受裸 str,只能是用户原文 / agent role / 系统角色 / 模型名。
    objective_kind: Literal["user_text", "agent_role", "system_role", "model_name"]
    objective: str = ""
    # summary 是 reducer 派生的人话摘要(如 "started" / "respond" / "tool_call")。
    summary: str = ""


__all__ = [
    "PhaseFoldPayload",
    "RequestHeader",
    "ThinkingRecord",
    "ToolCallRecord",
    "ToolResultRecord",
    "ToolSchema",
]
