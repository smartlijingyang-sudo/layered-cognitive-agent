"""事件 v2 契约 —— 单一发送者 + 闭集 category + pydantic payload（ADR-0179）。

``contracts/`` 不依赖 ``plugins/``；本模块只描述协议骨架，发送者实现与消费者
实现均在 ``lca/plugins/events/``。

业务方一行发送入口::

    from lca.contracts.event_v2 import (
        EventCategory, DelegationCacheHit, publish,
    )
    publish(DelegationCacheHit(callee_role=..., subtask_preview=..., step=...))

sender 内部负责：构造 Event、推导 plane、生成 EventRef、路由、双写。

不变量（参见 ADR-0179）：
- E1：category 闭集，无裸字符串。
- E4：构造与发送分离 —— 业务方构造 pydantic payload（**不**构造 Event）。
- E5：协议与实现解耦（本模块仅类型 + 公开 ``publish`` 模块函数）。
- E10：业务方只 import 此处或 ``lca.plugins.events``。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

# ── 闭集：category 与 plane ──────────────────────────────────────────────


class EventCategory(str, Enum):
    """事件类别闭集（ADR-0179 §Event 模型）。新增必须有 ADR。"""

    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    TASK_CREATED = "task.created"
    TEAM_CASTING = "team.casting"
    TEAM_DELEGATION = "team.delegation"
    PERCEPTION = "perception"
    GATE = "gate"
    TOOL = "tool"
    LLM = "llm"
    SANDBOX = "sandbox"
    MEMORY = "memory"
    CONTROL = "control"
    PLUGIN = "plugin"
    BOOT = "boot"
    RUNTIME_OBSERVED = "runtime.observed"
    EXCEPTION = "exception"


class EventPlane(str, Enum):
    """事件语义平面（沿用 ADR-0063 的三平面，不变）。"""

    SURFACE = "surface"
    STRUCTURAL = "structural"
    EXPLANATION = "explanation"


# 试点 category 与 plane 的映射。
_CATEGORY_DEFAULT_PLANE: dict[EventCategory, EventPlane] = {
    EventCategory.TEAM_DELEGATION: EventPlane.STRUCTURAL,
}


def default_plane(category: EventCategory) -> EventPlane:
    """由 category 推导 plane。闭集之外的 category 抛 ValueError。"""
    try:
        return _CATEGORY_DEFAULT_PLANE[category]
    except KeyError as exc:
        msg = (
            f"EventCategory.{category.name} 未登记 plane 映射；"
            "新增 category 必须在 ADR-0179 §Category 中登记 default_plane"
        )
        raise ValueError(msg) from exc


# ── Pydantic payload 集（ADR-0179 E11：业务方构造 typed model）─────────


class EventPayload(BaseModel):
    """所有事件 payload 的基类。

    业务方构造一个具体 ``EventPayload`` 子类（typed 字段），调 ``publish``；
    sender 读 ``payload.category`` 决定路由，不要求业务方传 category。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class DelegationCacheHit(EventPayload):
    """试点 payload：委派幂等短路命中（对应旧 DelegationCacheHit）。"""

    category: EventCategory = EventCategory.TEAM_DELEGATION
    callee_role: str
    subtask_preview: str
    step: int


# ── Event 与 EventRef（sender 内部构造，业务方不直接 import）────────────


from pydantic import Field  # noqa: E402


class EventRef(BaseModel):
    """发布返回的轻量引用（事件 id、所属 trace、时间戳）。"""

    model_config = ConfigDict(frozen=True)

    event_id: str
    trace_id: str = ""
    ts: float


class Event(BaseModel):
    """事件 v2 模型（sender 内部构造）。

    业务方**不**直接构造 Event；构造 ``EventPayload`` 子类后调 ``publish``，
    sender 内部补 plane / trace_id 并包装为 Event。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: EventCategory
    plane: EventPlane
    payload: EventPayload
    trace_id: str = ""
    causation_refs: tuple[str, ...] = Field(default_factory=tuple)


# ── Protocols：发送者与消费者 ────────────────────────────────────────────


class EventSenderProtocol:
    """保留作为类型占位；具体方法定义在 sender.py（避免循环 import）。

    业务方**不**直接持有 EventSender 实例 —— ``publish(payload)`` 模块函数
    内部委托给进程级 sender，业务方对此透明。
    """


class EventConsumerProtocol:
    """消费者协议占位；具体见 ``lca.plugins.events.consumers``。"""


# ── 业务方一行发送入口 ──────────────────────────────────────────────────


def publish(payload: EventPayload) -> EventRef | None:
    """业务方一行发送入口（ADR-0179 P2：业务方 ≤ 1 行，构造 pydantic payload）。

    用法::

        publish(DelegationCacheHit(callee_role=..., subtask_preview=..., step=...))

    sender 未 boot 时返回 None；业务方**不**必判断 None（返回值仅供自检）。
    helper 委托 sender 构造 Event + 推导 plane + 路由 + 双写（试点期）。
    """
    from lca.plugins.events.sender import publish as _publish_impl

    return _publish_impl(payload)


# ── 试点范围显式记录（用于 lint 守护）─────────────────────────────────────

PILOT_PAYLOADS: tuple[type[EventPayload], ...] = (DelegationCacheHit,)
"""试点 PR 仅覆盖 DelegationCacheHit；其余 payload 在后续 PR 补齐。"""

PILOT_CATEGORIES: frozenset[EventCategory] = frozenset(
    {payload.model_fields["category"].default for payload in PILOT_PAYLOADS}
)
"""由 PILOT_PAYLOADS 派生；防止 pilot category 与 pilot payload 漂移。"""


__all__ = [
    "PILOT_CATEGORIES",
    "PILOT_PAYLOADS",
    "DelegationCacheHit",
    "Event",
    "EventCategory",
    "EventConsumerProtocol",
    "EventPayload",
    "EventPlane",
    "EventRef",
    "EventSenderProtocol",
    "default_plane",
    "publish",
]
