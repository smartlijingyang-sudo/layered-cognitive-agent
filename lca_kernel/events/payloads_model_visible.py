"""Model-visible spine event payload（ADR-0185 §3.3）。

承载两类 spine EP 的 typed payload:
- :class:`SpineLlmRequestHeaderPayload` — LLM 调用边界真实 prompt 投影
- :class:`SpineLlmRequestHeaderAssistantPayload` — LLM 实际产出

对齐 deepseek-harness ``packages/core/session/src/types.ts`` 的
``SpineLlmRequestHeaderPayload`` 字段语义 + ``request/header.assistant``
semantic inspect 投影。fold 重建见 PR-0 落地的 :mod:`lca_kernel.events.fold`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import ConfigDict

from lca.contracts.event import Category, EventPayload
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.observability.loop_cursor_payloads import ToolSchema

ReasonType = Literal["initial", "resume", "change", "series"]
"""Fold reason 闭集（ADR-0185 §3.5）。

- ``initial`` — 本 step 首条 header（无 previous）。
- ``resume`` — cursor.snapshot.inherited_from_step 非 None。
- ``change`` — ``headerEquals(prev, current) == False``（任意字段差）。
- ``series`` — 同 header 但开新 series（retry 路径，PR-2 publisher 内部决定）。
"""

if TYPE_CHECKING:
    # PR-0 在 ``lca_kernel/events/types.py`` 落地以下占位类型；本 PR
    # 仅 stub 让 mypy --strict 通过；pydantic 在 PR-0 落地后按真实类型解析。
    from typing import Any

    AssistantRequestConfig = Any
    MessageDict = Any
    ToolCallDict = Any
    UsageDict = Any


class SpineLlmRequestHeaderPayload(EventPayload):
    """LLM 调用边界真实 prompt 投影（ADR-0185 §3.3）。

    字段语义:
    - ``step_id`` / ``incarnation`` — 由 cursor.snapshot 注入;业务路径不填。
    - ``config`` — AssistantRequestConfig(provider/model/sampling 等);
      forward-ref,PR-0 在 :mod:`lca_kernel.events.types` 落地。
    - ``system`` — 已渲染的 system prompt 原文(str);与 messages 解耦,
      修复 ADR-0169 Note ``2026-09-03-model-visible-incomplete-projection``
      第 3 BUG(system 错塞到 ``messages[0].role=user``)。
    - ``tools`` — 当前可用工具 schema 序列(:class:`ToolSchema` 强类型)。
    - ``messages`` — 实际发给 LLM 的消息序列(MessageDict forward-ref)。
    - ``manifest`` — ContextManifest 或 None(无 manifest 路径)。
    - ``reason`` — fold reason 闭集 4 值(见 :data:`ReasonType`)。
    - ``previous_header_digest`` — 上一 header 的 ``sha256:<hex>``;
      None ⇒ 本 step 首条(对应 ``reason=initial``)。

    失败语义:必填字段缺失 → pydantic ValidationError。空 ``tools`` /
    空 ``messages`` 不抛(允许显式零长 tuple 表达"当前无工具 / 无消息")。
    时序:在 LLM adapter 调用前由 :class:`ModelVisibleHook.before_publish`
    构造并 publish;事件落 :file:`<run_id>.spine.jsonl` 唯一 SSOT。
    所有权:本 payload 由 ``lca.plugins.events.publishers.model_visible``(PR-2)
    唯一构造,业务路径(Brain / Reasoner / Body)不得自行 publish。
    外部后果:viewer / ``lca-ops explain`` / ``foldRequestHeader`` 从
    spine.jsonl 读本 payload 重建 prompt 上下文;无旁路文件依赖。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category = Category("spine.llm.request.header")

    step_id: str
    incarnation: int
    config: "AssistantRequestConfig"  # noqa: UP037  # PR-0 在 lca_kernel.events.types 落地
    system: str
    tools: tuple["ToolSchema", ...]  # noqa: UP037  # forward-ref 同 config
    messages: tuple["MessageDict", ...]  # noqa: UP037  # forward-ref 同 config
    manifest: "ContextManifest | None"  # noqa: UP037  # forward-ref 同 config
    reason: ReasonType
    previous_header_digest: str | None


class SpineLlmRequestHeaderAssistantPayload(EventPayload):
    """LLM 实际产出投影（ADR-0185 §3.3）。

    字段语义:
    - ``step_id`` / ``incarnation`` — 与对应 request/header 一致。
    - ``assistant_content`` — LLM 本次产出的文本回复。
    - ``tool_calls`` — LLM 决策的工具调用序列(ToolCallDict forward-ref);
      空 tuple 表达"无工具调用"。
    - ``finish_reason`` — LLM provider 的 finish_reason 原文
      (stop / length / tool_calls 等,不做归一化)。
    - ``usage`` — token 计数(UsageDict forward-ref)。
    - ``header_digest`` — 关联回 request/header 的 ``sha256:<hex>``,
      便于 fold 重建时按 digest 配对。

    失败语义:必填字段缺失 → pydantic ValidationError。空 tool_calls 不抛。
    时序:在 LLM adapter 调用完成(流式 yield 结束)后由
    :class:`ModelVisibleHook.after_dispatch` 构造并 publish。
    所有权:本 payload 由 ``lca.plugins.events.publishers.model_visible``
    唯一构造。修复 ADR-0169 Note 第 1 BUG(assistant 没投影)。
    外部后果:viewer 与 explain 工具读本 payload 渲染模型回复与工具决策;
    与 ``spine.tool.*`` 不重叠(后者承担 tool 执行证据,本 payload 承担
    "模型可见上下文"语义)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category = Category("spine.llm.request.header.assistant")

    step_id: str
    incarnation: int
    assistant_content: str
    tool_calls: tuple["ToolCallDict", ...]  # noqa: UP037  # PR-0 落地
    finish_reason: str
    usage: "UsageDict"  # noqa: UP037  # PR-0 落地
    header_digest: str


__all__ = [
    "ReasonType",
    "SpineLlmRequestHeaderAssistantPayload",
    "SpineLlmRequestHeaderPayload",
]
