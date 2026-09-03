"""事件层 v2 协议 —— ADR-0180 配套。

机制实现见 :mod:`lca_kernel.events`（kernel 元层插件）。
本模块只描述协议骨架：Category 闭集、EventPayload pydantic 基类、Plane 闭集。

不变量：
- D2：Category 由机制在 boot 时从 ``lca_kernel/events/config/**/*.yaml`` 加载；
       本枚举给出试点最小闭集，PR 2–13 逐个补齐。
- D3：每个 EventPayload 必须声明 ``category`` 字段，子类覆盖 default。
- D4：本模块不导出 send/subscribe；那由机制 :class:`lca_kernel.events.mechanism.EventMechanism` 暴露。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

# ── 闭集：category 与 plane ──────────────────────────────────────────────


class Category(str, Enum):
    """事件 category 闭集（ADR-0180 D2）。

    本枚举是协议层最小集；机制 boot 时从 ``lca_kernel/events/config/**/*.yaml``
    加载完整 SSOT 矩阵，运行期拒收未登记的 category。
    新增必须有 ADR + 配套 yaml 行。
    """

    # business/team
    TEAM_CASTING_STARTED = "team.casting.started"
    TEAM_CASTING_COMPLETED = "team.casting.completed"
    TEAM_CASTING_FAILED = "team.casting.failed"
    TEAM_DELEGATION_ISSUED = "team.delegation.issued"
    TEAM_DELEGATION_COMPLETED = "team.delegation.completed"
    TEAM_DELEGATION_CACHE_HIT = "team.delegation.cache_hit"
    TEAM_MESSAGE_PUBLISHED = "team.message.published"
    # observability/spine — ADR-0181 试点 1 个；PR-2 全量补
    SPINE_COGNITION_BRAIN_PERCEIVE_START = "spine.cognition.brain.perceive.start"


class Plane(str, Enum):
    """事件语义平面（沿用 ADR-0063 三平面）。"""

    SURFACE = "surface"
    STRUCTURAL = "structural"
    EXPLANATION = "explanation"
    OBSERVABILITY = "observability"


# 试点 category 与 plane 的映射（与 yaml SSOT 保持同步；boot 时机制会校验一致）。
CATEGORY_DEFAULT_PLANE: dict[Category, Plane] = {
    Category.TEAM_DELEGATION_CACHE_HIT: Plane.STRUCTURAL,
    Category.SPINE_COGNITION_BRAIN_PERCEIVE_START: Plane.OBSERVABILITY,
}


def default_plane(category: Category) -> Plane:
    """由 category 推导 plane；未登记 → ValueError。"""
    try:
        return CATEGORY_DEFAULT_PLANE[category]
    except KeyError as exc:
        msg = f"Category.{category.name} 未登记 plane 映射；新增必须在 yaml + 本枚举同步登记"
        raise ValueError(msg) from exc


# ── Pydantic payload 集（D3：业务方构造 typed payload）─────────────────


class EventPayload(BaseModel):
    """所有事件 payload 的基类。

    业务方构造一个具体子类（typed 字段），调机制 :func:`EventMechanism.send`；
    机制读 ``payload.category`` 决定路由，不要求业务方传 category。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category
    """子类必须覆盖：声明本 payload 归属的 category 闭集值。"""


class TeamDelegationCacheHit(EventPayload):
    """试点 payload：委派幂等短路命中（对应旧 DelegationCacheHit）。

    publishers（SSOT yaml）: ``delegation_cache``
    subscribers（SSOT yaml）: ``journal_sink``, ``console_projector``, ``cursor_consumer``
    """

    category: Category = Category.TEAM_DELEGATION_CACHE_HIT
    callee_role: str
    subtask: str
    step: int


# ── 试点范围显式记录（用于 lint 守护）─────────────────────────────────────

PILOT_PAYLOADS: tuple[type[EventPayload], ...] = (TeamDelegationCacheHit,)
"""试点 PR 仅覆盖 TeamDelegationCacheHit；其余 payload 在后续 PR 补齐。"""

PILOT_CATEGORIES: frozenset[Category] = frozenset(
    {payload.model_fields["category"].default for payload in PILOT_PAYLOADS}
)
"""由 PILOT_PAYLOADS 派生；防止 pilot category 与 pilot payload 漂移。"""


__all__ = [
    "PILOT_CATEGORIES",
    "PILOT_PAYLOADS",
    "Category",
    "EventPayload",
    "Plane",
    "TeamDelegationCacheHit",
    "default_plane",
]
