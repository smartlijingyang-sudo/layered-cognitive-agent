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
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from lca.contracts.models.core.tool import ToolManifest


@dataclass(frozen=True)
class ThinkingRecord:
    content_digest: str
    content_path: str | None
    token_count: int | None
    thinking_kind: Literal[
        "reasoning",
        "final_response",
        "compaction",
        "tool_call_response",
        "tool_use_response",
    ]
    """Thinking record 闭集(ADR-0185 spec §2.4 P4)。

    - ``reasoning`` —— 模型内部推理(无对外工具调用)
    - ``final_response`` —— 模型产出的纯文本回复
    - ``compaction`` —— 上下文压缩阶段
    - ``tool_call_response`` —— 模型产出含 tool_calls;fold 重建时按
      ``SpineLlmRequestHeaderAssistantPayload.tool_calls`` 长度 > 0
      分类,不再打 ``final_response``(修复 spec §0.3 "thinking_kind=
      final_response 但实际是 tool_call" BUG)
    - ``tool_use_response`` —— fold 折叠后看到的同 tool_call_response,
      保留区分值让 caller(doctpr / viewer)按 fold 状态判定;

    修复前后:旧 capture 一律打 ``final_response``;P4 后 producer
    透传 ``tool_call_response`` / ``tool_use_response``,fold 折叠
    后的最终 thinking_kind 由 producer 端在调用前判定(见 spec §2.4
    "P4 必须在 P0 之后才能由 fold 派出来")。

    delete-when:N/A(纯加法,后续 PR-2 publisher fold 状态、PR-3
    viewer 重建、PR-4 删旁路文件都依赖本模块做语义锚点)。
    """


@dataclass(frozen=True)
class ToolCallRecord:
    """cursor 侧 tool_call 记录。

    - ``tool_name`` —— 工具名(主字段,canonical)
    - ``call_seq`` —— cursor 内自增,保留。
    - ``args_digest`` —— **deprecated**(ADR-0185 spec §2.5 P5)。
      digest 引用;原承担 sidecar 文件指针。保留 1 个 minor 版本以兼容
      ``StdLoopCursor.record_tool_call`` + fold / spine 现有 consumer;
      caller 应读 ``tool_name`` + 由 caller 端 caller-projected 字段。
      delete-when:下个 minor 版本后,或所有 caller 迁移完毕时。
      tracking: ADR-0185 spec §2.5 P5。
    - ``args_payload_path`` —— 同上 deprecated(原 sidecar payload path)。

    字段命名冻结(ADR-0185 spec §2.5):``tool_name`` / ``call_seq`` 是
    canonical,``args_digest`` / ``args_payload_path`` 下个 minor 版本删。
    """

    tool_name: str
    call_seq: int  # cursor 内自增
    # COMPAT(delete-when: 下个 minor 版本,或所有 caller 迁完;
    #   tracking: ADR-0185 spec §2.5 P5)
    args_digest: str = ""
    # COMPAT(delete-when: 下个 minor 版本,或所有 caller 迁完;
    #   tracking: ADR-0185 spec §2.5 P5)
    args_payload_path: str | None = None


@dataclass(frozen=True)
class ToolResultRecord:
    tool_name: str
    result_digest: str
    result_path: str | None
    outcome: Literal["ok", "failure", "timeout", "denied"]


@dataclass(frozen=True)
class RequestHeader:
    """cursor 注入 step_id / incarnation;业务路径不能填(ADR-0169 D4)。

    字段命名冻结(ADR-0185 spec §2.5 P5):

    - ``messages_digest`` / ``messages_path`` —— 唯一权威;同时承担
      旧 ``system_digest`` / ``system_path`` 的语义(system 文本已合并
      进 messages.json,见 ADR-0176 D4)。
    - ``system_digest`` / ``system_path`` —— **deprecated**;保留1个
      minor 版本以兼容 sidecar(`StdModelVisibleCapture` / `StdReasonerPromptCapture`
      / `ModelVisibleLLMAdapter`)及其测试,SA-3 删旁路文件时一并
      删这两个字段。caller 应读 ``messages_*`` 字段。
    """

    step_id: str
    incarnation: int
    reason: Literal["initial", "next_step", "series", "change", "inherited"]
    model: str
    tools_digest: str
    tools_path: str
    messages_digest: str
    messages_path: str
    manifest_digest: str
    manifest_path: str
    inherited_from_step: str | None = None
    # COMPAT(delete-when: SA-3 删旁路文件 + 旁路测试一并落地;或 1 个
    #   minor 版本后强制退役,tracking: ADR-0185 spec §2.5 P5)
    system_digest: str = ""
    system_path: str = ""


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

    @staticmethod
    def from_manifest(manifest: ToolManifest, api_name: str | None = None) -> ToolSchema:
        """LobeHub 风格 ``ToolManifest`` → OpenAI 风格 ``ToolSchema`` 单向桥。

        一个 manifest 可声明多个 ``api`` 条目；``api_name`` 选定其一，
        省略时要求 manifest 恰好含一个 api，否则抛 ``ValueError``。
        ``manifest.parameters``（typed ``ParameterSpec``）与 ``ui_hint``
        是 renderer 侧概念（ADR-0101 §5.2），不进 LLM 边界 schema，仅在
        ``_extras`` 留 identifier 供 trace，不参与 digest。
        """
        apis = tuple(getattr(manifest, "api", ()) or ())
        if api_name is not None:
            selected = next((api for api in apis if getattr(api, "name", "") == api_name), None)
            if selected is None:
                raise ValueError(
                    f"ToolManifest {getattr(manifest, 'identifier', '?')!r} has no api {api_name!r}"
                )
        elif len(apis) == 1:
            selected = apis[0]
        else:
            raise ValueError(
                f"ToolManifest {getattr(manifest, 'identifier', '?')!r} declares "
                f"{len(apis)} apis; pass api_name to select one"
            )
        return ToolSchema(
            name=str(getattr(selected, "name", "")),
            description=str(getattr(selected, "description", "") or ""),
            parameters=dict(getattr(selected, "parameters", None) or {}),
            _extras={"identifier": str(getattr(manifest, "identifier", ""))},
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
