# -*- coding: utf-8 -*-
"""主动消息裁决契约：请求与裁决结果。

裁决层（cognition/proactive/worthiness.WorthinessGate）是纯函数：
``ProactiveRequest -> WorthinessVerdict``，决策矩阵见 gate 实现。

规则摘要（ADR-0260 对齐；ADR-0264 §4① 调用方声明 + gate 交叉校验）：
- 调用方声明期望裁决（declared），gate 只做 downgrade-only 交叉校验
  （只能往更不打扰方向移动，绝不升级）；
- requested=True 必须携带可验证的 request_ref（须在 trigger 上下文
  背书的 known_request_refs 集合中），校验通过 → 必达（DELIVER_CHAT），
  回发起上下文；校验不过 → 按未要求处理；
- 未被要求的 → 只有"实质新信息且值得打断"才推聊天，
  否则安静面（DELIVER_QUIET）或静默（SILENT，合法默认项）；
- 内容命中凭证模式 → 整条拒绝（REJECTED，最高抑制）+ 调用方记 warning，
  不做脱敏写入（幻觉比不记更危险）。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lca.contracts.models.proactive.message import DeliveryTarget, ProactiveMessage


class VerdictKind(str, Enum):
    """裁决结果种类。"""

    DELIVER_CHAT = "deliver_chat"
    DELIVER_QUIET = "deliver_quiet"
    SILENT = "silent"
    REJECTED = "rejected"


class ProactiveRequest(BaseModel):
    """一次主动消息裁决请求。

    调用方声明 + gate 交叉校验（ADR-0264 §4①）：
    - ``declared``：调用方声明的期望裁决；gate 只做 downgrade-only 校验；
    - ``requested=True`` 必须携带可验证的 ``request_ref``，且该引用在
      trigger 上下文背书的 ``known_request_refs`` 中，否则按未要求处理。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: ProactiveMessage = Field(..., description="待裁决的消息")
    target: DeliveryTarget = Field(..., description="期望投递落点")
    requested: bool = Field(
        ...,
        description="调用方声称的用户明确要求/触发；须经 request_ref 机械校验，通过才必达",
    )
    declared: VerdictKind = Field(
        ...,
        description="调用方声明的期望裁决；gate 只做 downgrade-only 交叉校验（只能降不能升）",
    )
    request_ref: str | None = Field(
        default=None,
        description="requested=True 时必填的引用 ID（如 onboarding-completed:<user_id>）；须在 known_request_refs 中",
    )
    known_request_refs: tuple[str, ...] = Field(
        default=(),
        description="trigger 上下文背书的可验证引用集合；request_ref 须是其成员",
    )
    is_novel: bool = Field(default=True, description="是否实质新信息")
    is_routine: bool = Field(default=False, description="是否例行事项")
    has_memory_source: bool = Field(default=True, description="是否有可用记忆源")
    worth_interrupting: bool = Field(
        default=False,
        description="是否值得打断用户（未被要求时推聊天的唯一理由）",
    )

    @model_validator(mode="after")
    def validate_declared(self) -> ProactiveRequest:
        if self.declared == VerdictKind.REJECTED:
            raise ValueError(
                "declared 只能是投递意向（deliver_chat/deliver_quiet/silent）；"
                "REJECTED 是 gate 专用的抑制裁决，调用方无权声明"
            )
        return self


class WorthinessVerdict(BaseModel):
    """裁决结果：投哪里 + 为什么。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: VerdictKind = Field(..., description="裁决结果种类")
    reason: str = Field(..., description="人类可读的裁决理由（审计用）")
    annotate_unretrieved: bool = Field(
        default=False,
        description="为 True 时投递内容须标注未经检索",
    )


__all__ = [
    "ProactiveRequest",
    "VerdictKind",
    "WorthinessVerdict",
]
