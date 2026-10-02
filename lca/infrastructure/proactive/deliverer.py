# -*- coding: utf-8 -*-
"""ProactiveDeliverer：主动消息投递层。

职责单一：把裁决通过的消息 append 进目标 session 的
``surface/assistant_message`` 事件——与前端读的是同一份 session log
（``derive_messages()``），不新开消息协议。

- SESSION_APPEND：从 SessionStore 取 session，不存在则创建（幂等），
  append 事件。事件 data 复用 run 路径的 surface taxonomy，
  ``turn=-1`` 标记非 run 上下文的主动消息，``proactive=true`` 供前端区分。
- RESPONSE_CARRIED：不经过 session，由调用方把 ``carried_message``
  塞进 HTTP 响应（见 routes_onboarding.naming_settle）。

分层约束：只依赖 contracts + Session 的公开 ``append`` 方法，
不碰任何私有属性，不跨层直调。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from lca.contracts.models.proactive.message import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveMessage,
)

_log = logging.getLogger(__name__)

# 非 run 上下文主动消息的 turn 哨兵：与正常 run 的 turn>=0 区分。
PROACTIVE_TURN = -1

# surface 事件类型：复用 run 路径的 taxonomy（ADR-0226 §B）。
SURFACE_ASSISTANT_MESSAGE = "surface/assistant_message"


class SessionLike(Protocol):
    """投递所需的 Session 最小公开接口（避免依赖具体实现类）。"""

    @property
    def id(self) -> str: ...
    def append(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> Any: ...


class SessionStoreLike(Protocol):
    """投递所需的 SessionStore 最小公开接口。"""

    def get(self, session_id: str) -> SessionLike | None: ...
    def create(self, session_id: str | None = None) -> SessionLike: ...


class ProactiveDeliverer:
    """主动消息投递器：session append 是唯一的写路径。"""

    def __init__(self, session_store: SessionStoreLike | None = None) -> None:
        self._store = session_store

    def deliver(
        self,
        message: ProactiveMessage,
        target: DeliveryTarget,
        *,
        annotate_unretrieved: bool = False,
    ) -> dict[str, Any]:
        """投递一条消息，返回投递回执（fail-loud，不静默吞错）。

        precondition：target.kind 为 SESSION_APPEND 时 session_id 非空
        （contracts 层已校验）。失败时抛错，由调用方决定重试/死信。
        """
        if target.kind == DeliveryTargetKind.RESPONSE_CARRIED:
            return {
                "delivered": True,
                "kind": target.kind.value,
                "carried_message": {
                    "id": message.id,
                    "role": message.role,
                    "content": self._render(message, annotate_unretrieved),
                    "source": message.source.value,
                },
            }
        return self._append_to_session(message, target, annotate_unretrieved)

    def _append_to_session(
        self,
        message: ProactiveMessage,
        target: DeliveryTarget,
        annotate_unretrieved: bool,
    ) -> dict[str, Any]:
        assert target.session_id is not None
        if self._store is None:
            raise RuntimeError("SESSION_APPEND 需要 session_store")
        session = self._store.get(target.session_id)
        if session is None:
            session = self._store.create(target.session_id)
            _log.info(
                "proactive.session_created session_id=%s message_id=%s",
                target.session_id,
                message.id,
            )
        event = session.append(
            SURFACE_ASSISTANT_MESSAGE,
            {
                "turn": PROACTIVE_TURN,
                "step": 0,
                "role": message.role,
                "content": self._render(message, annotate_unretrieved),
                "tool_calls": None,
                "usage": None,
                "proactive": True,
                "proactive_id": message.id,
                "proactive_source": message.source.value,
            },
            surface_op="assistant_message",
            actor="proactive",
        )
        _log.info(
            "proactive.delivered session_id=%s message_id=%s seq=%s",
            target.session_id,
            message.id,
            event.seq,
        )
        return {
            "delivered": True,
            "kind": target.kind.value,
            "session_id": target.session_id,
            "seq": event.seq,
        }

    @staticmethod
    def _render(message: ProactiveMessage, annotate_unretrieved: bool) -> str:
        content = message.content
        if annotate_unretrieved:
            content = f"{content}\n\n（本次内容未经持久记忆检索，仅供参考）"
        return content


__all__ = ["PROACTIVE_TURN", "SURFACE_ASSISTANT_MESSAGE", "ProactiveDeliverer"]
