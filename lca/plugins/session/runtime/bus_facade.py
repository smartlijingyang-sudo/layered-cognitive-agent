"""Session 的 EventBus Protocol 适配面（publish append / observe callback）。

runtime :class:`~lca.plugins.session.runtime.session.Session` 的公开面是
``append(event_type, data) → SessionEvent`` 与
``observe(SessionObserver) → cancel``。publisher / consumer 接缝要的是
``append(payload, *, producer) → EventRef`` 与
``observe(plugin, callback)``。本 facade 只做形状适配，不拥有日志。

契约:

- ``append`` 把 ``payload.category`` 写成 ``event_type``，其余可 JSON 字段
  写成 ``data``（不含 category）；``producer`` 不入日志（鉴权仍在
  EventBus fallback）。返回由 :class:`SessionEvent` 合成的 :class:`EventRef`
  （``event_id = "{session.id}:{seq}"``，``category = event.type``）。
- ``observe`` 把 ``callback(payload, ref)`` 登记为 :class:`SessionObserver`；
  派发时优先交 in-flight 的原 payload（跨 facade 实例共享），否则从
  ``SessionEvent`` 投影。单个 callback 失败 contained，不打断后续观察者、
  不回滚已提交事件。
- 时序跟随 Session：事件入日志先于 observer fire。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Any, cast

import structlog

from lca.contracts.event import EventPayload
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.bus import EventRef
from lca_kernel.events.session import SessionEvent, SessionProtocol

_log = structlog.get_logger(__name__)

# append 进行中的原 payload，按 Session 身份索引。Session 拒重入，同一
# session 同时只有一条 in-flight；多个 facade 包同一 Session 时共享此槽，
# 保证 observe 接缝拿到 publisher 写入的原对象。
_inflight_payload: dict[int, object] = {}

__all__ = ["SessionBusFacade", "as_bus_facade"]


def as_bus_facade(session: object | None) -> object | None:
    """runtime Session 包成 bus Protocol；其余对象（含本 facade）原样返回。"""
    if session is None or isinstance(session, SessionBusFacade):
        return session
    if isinstance(session, Session):
        return SessionBusFacade(session)
    return session


def _category_str(payload: object) -> str:
    category = getattr(payload, "category", None)
    if category is None:
        raise TypeError(f"EventPayload 必须提供 category；got {type(payload).__name__}")
    value = getattr(category, "value", None)
    if isinstance(value, str) and value:
        return value
    text = str(category)
    if not text:
        raise ValueError("EventPayload.category 不能为空")
    return text


def _payload_data(payload: object) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump(mode="json")
        if not isinstance(dumped, dict):
            raise TypeError(f"EventPayload.model_dump 必须返回 dict；got {type(dumped).__name__}")
        dumped.pop("category", None)
        return dumped
    if isinstance(payload, Mapping):
        data = dict(payload)
        data.pop("category", None)
        return data
    raise TypeError(f"append payload 必须是 EventPayload 或 Mapping；got {type(payload).__name__}")


def _event_ref(session: SessionProtocol, event: SessionEvent) -> EventRef:
    return EventRef(
        event_id=f"{session.id}:{event.seq}",
        category=event.type,
        trace_id="",
        ts=event.time / 1000.0,
        persisted=False,
        subscriber_count=0,
    )


def _project_payload(event: SessionEvent) -> object:
    """无 in-flight 原对象时的最小投影：``category = event.type`` + data 字段。"""
    fields = dict(event.data)
    fields["category"] = event.type
    return SimpleNamespace(**fields)


class SessionBusFacade:
    """把 runtime Session 暴露成 publisher / observer 接缝的 bus Protocol。"""

    def __init__(self, session: Session) -> None:
        if not isinstance(session, Session):
            raise TypeError(f"SessionBusFacade 只包 runtime Session；got {type(session).__name__}")
        self._session = session

    @property
    def session(self) -> Session:
        """被适配的 runtime Session（日志真值仍在该对象上）。"""
        return self._session

    def append(self, payload: object, *, producer: object) -> EventRef:
        """映射 payload → Session.append；返回合成 EventRef。

        precondition：``payload`` 有非空 ``category``，其余字段可无损 JSON
        序列化。失败语义：校验失败上抛、日志不变；observer 失败 contained。
        ``producer`` 被接受以匹配接缝签名，不写入 Session。
        """
        del producer
        event_type = _category_str(payload)
        data = _payload_data(payload)
        session = self._session
        key = id(session)
        previous = _inflight_payload.get(key)
        _inflight_payload[key] = payload
        try:
            event = session.append(event_type, data)
            return _event_ref(session, event)
        finally:
            if previous is None:
                _inflight_payload.pop(key, None)
            else:
                _inflight_payload[key] = previous

    def observe(
        self,
        plugin: type,
        callback: Callable[[EventPayload, EventRef], None],
    ) -> Callable[[], None]:
        """登记 ``callback(payload, ref)``；返回幂等 cancel。

        失败语义：``callback`` 不可调用则登记时抛 ``TypeError``；派发时单个
        callback 抛错被 contained（记日志后继续）。时序：只对后续 append 生效。
        """
        if not callable(callback):
            raise TypeError(f"observe callback 必须可调用；got {type(callback).__name__}")
        plugin_name = getattr(plugin, "__name__", str(plugin))

        def adapter(_session: SessionProtocol, event: SessionEvent) -> None:
            inflight = _inflight_payload.get(id(self._session))
            payload = inflight if inflight is not None else _project_payload(event)
            ref = _event_ref(self._session, event)
            try:
                callback(cast("EventPayload", payload), ref)
            except Exception:
                _log.warning(
                    "session.bus_facade.observer.failed",
                    plugin=plugin_name,
                    session_id=self._session.id,
                    seq=event.seq,
                    event_type=event.type,
                    exc_info=True,
                )

        return self._session.observe(adapter)
