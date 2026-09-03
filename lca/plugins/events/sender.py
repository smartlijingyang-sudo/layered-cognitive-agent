"""事件 v2 发送者（ADR-0179 唯一 SSOT）。

业务方只构造 ``EventPayload``（pydantic），调模块函数 ``publish(payload)``。
本模块负责：构造 Event、推导 plane、生成 EventRef、路由、双写（试点期）。

发送者职责（E2 极简）：
1. 业务方给 pydantic ``EventPayload``；
2. sender 内部读 ``payload.category``、推 ``default_plane``、构造 ``Event``；
3. 分配 ``event_id`` / ``ts``，返回 ``EventRef``；
4. 委托 ``EventRouterImpl.dispatch`` 路由给订阅者；
5. （试点期）双写到旧 journal backend，让现有 console projector 仍能渲染
   ``DelegationCacheHit`` —— 删除条件见 ADR-0179 §删-when。

发送者**不**校验 schema、不感知消费者、不持有 49 字段映射。
"""

from __future__ import annotations

import logging
import time
import warnings
from typing import TYPE_CHECKING

from lca.contracts.atoms.ids import new_id
from lca.contracts.event_v2 import (
    DelegationCacheHit as _DelegationCacheHitPydantic,
)
from lca.contracts.event_v2 import Event, EventPayload, EventRef, default_plane
from lca.contracts.models.observability.journal import (
    DelegationCacheHit as _LegacyDelegationCacheHit,
)

if TYPE_CHECKING:
    from lca.plugins.events.router import EventRouterImpl

_log = logging.getLogger(__name__)


# ── 进程级单例（试点）──────────────────────────────────────────────────────
# plugins/ 不反向 import cognition/；business caller 通过模块函数 publish() 间接
# 拿到 sender，sender 由 manifest.setup_sender 末尾注册。
_active_sender: EventSenderImpl | None = None


def set_active_sender(sender: EventSenderImpl | None) -> None:
    """注册或清空进程级 sender。"""
    global _active_sender
    _active_sender = sender


def get_active_sender() -> EventSenderImpl | None:
    """返回当前 sender；未注册 = None。"""
    return _active_sender


# ── 业务方一行入口 ────────────────────────────────────────────────────────


def publish(payload: EventPayload) -> EventRef | None:
    """业务方一行发送入口（ADR-0179 P2）。

    用法::

        publish(DelegationCacheHit(callee_role=..., subtask_preview=..., step=...))

    sender 未 boot 时返回 None；业务方**不**必判断 None。
    """
    if _active_sender is None:
        return None
    return _active_sender.publish(payload)


# ── 发送者实现 ────────────────────────────────────────────────────────────


class EventSenderImpl:
    """v2 发送者（唯一 SSOT）。构造 Event、路由、双写——所有职责集中于此。"""

    def __init__(self, router: EventRouterImpl, *, dual_write_legacy: bool = True) -> None:
        self._router = router
        self._dual_write_legacy = dual_write_legacy

    def publish(self, payload: EventPayload) -> EventRef:
        """业务方入口：构造 Event → 路由 → 双写（旧协议试点期）。

        路由失败被 router 内部吞掉（记日志），**不**影响返回 ref。
        """
        category = payload.category
        event = Event(
            category=category,
            plane=default_plane(category),
            payload=payload,
        )
        ref = EventRef(
            event_id=new_id("evt"),
            trace_id="",
            ts=time.time(),
        )
        delivered = self._router.dispatch(event, ref)
        _log.debug(
            "EventSender.publish delivered",
            extra={
                "event_id": ref.event_id,
                "category": event.category.value,
                "consumers": delivered,
            },
        )
        if self._dual_write_legacy:
            self._dual_write(event)
        return ref

    def _dual_write(self, event: Event) -> None:
        """试点期双写到旧 journal backend。

        COMPAT(ADR-0179, delete-when: PR-25 + 双写计数 = 0)。
        当前仅 ``TEAM_DELEGATION / DelegationCacheHit`` 走双写；其余 category
        在试点期被忽略（无旧 path 兼容）。
        """
        if event.category.value != "team.delegation":
            return
        payload = event.payload
        # 试点只覆盖 DelegationCacheHit 这一种 pydantic payload；其余 TEAM_DELEGATION 子类型待后续 PR。
        if not isinstance(payload, _DelegationCacheHitPydantic):
            return
        try:
            legacy_event = _LegacyDelegationCacheHit(
                callee_role=payload.callee_role,
                subtask_preview=payload.subtask_preview,
                step=payload.step,
            )
        except Exception as exc:
            _log.warning("EventSender dual-write skipped: %s", exc)
            return
        # 通过现 facade.record 走旧路径；这是试点唯一允许的耦合面。
        try:
            from lca.infrastructure.observability.facade.facade import record
        except ImportError:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            record(legacy_event)


__all__ = ["EventSenderImpl", "get_active_sender", "publish", "set_active_sender"]
