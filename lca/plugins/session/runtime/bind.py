"""Bind a per-run Session onto publisher/observer ContextVar slots.

ADR-0186：Session 是事件 SSOT。本模块是 **run 边界** 装/卸槽的唯一实现
（Carrier 与 in-process spawn 共用）。webserver 不得再私有一份 bind。

``publish_via_session`` / observer catalog 要求 active Session；缺
``session.store`` 时返回 None（调用方仍会在首次 publish 时
``MissingPublishSessionError`` fail-loud，不再假装 EventBus 降级）。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from lca.contracts.event import EventPayload
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.plugins.events._session_observe import (
    EventObserverCallback,
    current_session,
    set_session,
)
from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.bus import EventRef
from lca_kernel.events.session import SessionEvent, SessionProtocol

_log = structlog.get_logger(__name__)

__all__ = [
    "BoundRunEventSession",
    "EventSessionBinder",
    "RunEventSessionBridge",
    "bind_run_event_session",
    "bind_run_event_session_from_store",
    "event_session_binder_from_scope",
    "unbind_run_event_session",
]


def _session_event_parts(payload: Any) -> tuple[str, dict[str, Any]]:
    """Project an EventBus payload into Session.append(type, data).

    SpineEventPayload keeps header/fold bytes in ``payload``; other
    EventPayload subclasses dump remaining fields. Failure: unknown
    shapes raise TypeError and leave the Session log unchanged.
    """
    category = getattr(payload, "category", None)
    event_type = getattr(category, "value", None) or (str(category) if category else "")
    if not event_type:
        event_type = type(payload).__name__

    inner = getattr(payload, "payload", None)
    if isinstance(inner, dict):
        return event_type, dict(inner)

    dump = getattr(payload, "model_dump", None)
    if callable(dump):
        data = dump(mode="json")
        if isinstance(data, dict):
            data.pop("category", None)
            return event_type, data

    if isinstance(payload, dict):
        return event_type, dict(payload)

    raise TypeError(f"cannot project payload {type(payload).__name__} into session event data")


def _event_ref_from_session(session: SessionProtocol, event: SessionEvent) -> EventRef:
    """Build the EventRef shape Session observers already receive."""
    return EventRef(
        event_id=f"{session.id}:{event.seq}",
        category=event.type,
        trace_id="",
        ts=event.time / 1000.0,
        persisted=False,
        subscriber_count=0,
    )


class RunEventSessionBridge:
    """Present a DSH Session as the publisher + observer ContextVar target.

    Ownership: one bridge per run; :func:`unbind_run_event_session` tears it
    down. Observer fire is contained by Session.append.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._payloads: dict[int, Any] = {}
        # append 进行中的原 payload；Session.append 同步 fire observer，
        # 必须在拿到 seq 写入 _payloads 之前就能被 observe 适配器读到。
        self._inflight_payload: Any | None = None

    @property
    def inner(self) -> Session:
        """Underlying DSH Session (in-process log owner)."""
        return self._session

    def append(self, payload: Any, *, producer: Any) -> EventRef:
        """Commit to Session log and return a synthetic EventRef.

        precondition: ``payload`` projects to JSON-serializable data.
        失败语义: Session 校验失败不改日志；成功则日志已 commit 且
        Session.observe 已同步派发。
        时序: 先置 ``_inflight_payload``，再 ``Session.append``（同步通知
        observer），再按 seq 固化到 ``_payloads``，返回与 observer 同形的
        EventRef。``producer`` 保留签名兼容，本桥不投递 EventBus。
        """
        del producer
        event_type, data = _session_event_parts(payload)
        previous = self._inflight_payload
        self._inflight_payload = payload
        try:
            event = self._session.append(event_type, data)
            self._payloads[event.seq] = payload
        finally:
            self._inflight_payload = previous
        return _event_ref_from_session(self._session, event)

    def observe(self, plugin: type, callback: EventObserverCallback) -> object:
        """Register an EventBus-shaped callback as a SessionObserver.

        时序: 只对后续 append 生效。``plugin`` 是注册名义，Session 观察面
        不按 plugin 鉴权。回调收到 append 时的原始 payload。
        """
        del plugin

        def _on_event(session: SessionProtocol, event: SessionEvent) -> None:
            payload = self._payloads.get(event.seq)
            if payload is None:
                payload = self._inflight_payload
            if payload is None or not isinstance(payload, EventPayload):
                return
            callback(payload, _event_ref_from_session(session, event))

        return self._session.observe(_on_event)


@dataclass(slots=True)
class BoundRunEventSession:
    """Run-local Session binding; disposer owns unbind + store.dispose."""

    store: Any
    bridge: RunEventSessionBridge
    publish_token: Any
    run_id: str
    spine_hook_token: Any = None


def bind_run_event_session_from_store(store: Any, run_id: str) -> BoundRunEventSession:
    """Create Session for ``run_id`` and occupy publish/observe slots.

    precondition: ``store.create`` returns :class:`Session`.
    失败语义: create 冲突 / 类型错误上抛（fail-loud）。
    """
    inner = store.create(run_id)
    if not isinstance(inner, Session):
        raise TypeError(f"session.store.create must return Session, got {type(inner).__name__}")
    bridge = RunEventSessionBridge(inner)
    token = set_publish_session(bridge)
    set_session(bridge)
    from lca.plugins.session.runtime.spine_hook import bind_bridge_spine_hook

    spine_hook_token = bind_bridge_spine_hook(bridge)
    return BoundRunEventSession(
        store=store,
        bridge=bridge,
        publish_token=token,
        run_id=run_id,
        spine_hook_token=spine_hook_token,
    )


def bind_run_event_session(ctx: Any, run_id: str) -> BoundRunEventSession | None:
    """Resolve ``session.store`` from ``ctx`` then bind.

    缺 ``session.store``: warning + 返回 None；首次 ``publish_via_session``
    仍会 ``MissingPublishSessionError``。
    """
    try:
        store = require_capability(ctx, "session.store")
    except MissingCapabilityError:
        _log.warning(
            "session.store.missing",
            run_id=run_id,
            detail="publish_via_session will fail-loud without bind",
        )
        return None
    return bind_run_event_session_from_store(store, run_id)


def unbind_run_event_session(bound: BoundRunEventSession | None) -> None:
    """Reset publish/observe slots and dispose the Session. Idempotent."""
    if bound is None:
        return
    if bound.spine_hook_token is not None:
        from lca.plugins.session.runtime.spine_hook import reset_bridge_spine_hook

        with contextlib.suppress(Exception):
            reset_bridge_spine_hook(bound.spine_hook_token)
    with contextlib.suppress(Exception):
        reset_publish_session(bound.publish_token)
    if current_session() is bound.bridge:
        set_session(None)
    with contextlib.suppress(Exception):
        bound.store.dispose(bound.run_id)


class EventSessionBinder:
    """Composition-injected run-boundary binder for CognitiveAgent.

    Carrier 已 bind 时 no-op（不 create、不 dispose）；仅在槽空时 create，
    并在退出时 unbind。Agent 不拥有 SessionStore 生命周期决策——只调用本
    binder。
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    @contextlib.contextmanager
    def bound(self, run_id: str) -> Iterator[BoundRunEventSession | None]:
        """Bind for ``run_id`` if publish slot empty; otherwise yield None."""
        if current_publish_session() is not None:
            yield None
            return
        bound = bind_run_event_session_from_store(self._store, run_id)
        try:
            yield bound
        finally:
            unbind_run_event_session(bound)


class _HasInject(Protocol):
    def inject(self, key: str) -> Any: ...


def event_session_binder_from_scope(scope: _HasInject) -> EventSessionBinder | None:
    """Build binder from booted scope; missing store → None."""
    try:
        store = scope.inject("session.store")
    except (KeyError, LookupError):
        return None
    return EventSessionBinder(store)
