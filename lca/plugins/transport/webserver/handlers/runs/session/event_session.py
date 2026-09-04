"""Bind a per-run DSH Session onto publisher/observer slots.

DSH :class:`~lca.plugins.session.runtime.session.Session` speaks
``append(type, data)`` / ``observe(observer)``. Publisher helper
:func:`publish_via_session` and observer helper
:func:`register_as_session_observer` speak ``append(payload, *, producer)``
and ``observe(plugin, callback)``. This module is the run-scoped adapter.

# COMPAT(delete-when: rg "EventBus.default().publish" event_session.py = 0
# 且 Bridge.append 不再 EventBus 双写, tracking: ADR-0186 PR-3f)
# append 在 Session 提交后再 EventBus.publish；consumer 已改走
# Session.observe 目录（set_session 挂上），双写仅服务仍挂在 bus 上的遗留面。
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import structlog

from lca.contracts.event import EventPayload
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.plugins.events._session_observe import (
    EventObserverCallback,
    current_session,
    set_session,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.bus import EventBus, EventRef
from lca_kernel.events.session import SessionEvent, SessionProtocol

_log = structlog.get_logger(__name__)

__all__ = [
    "BoundRunEventSession",
    "RunEventSessionBridge",
    "bind_run_event_session",
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


class RunEventSessionBridge:
    """Present a DSH Session as the publisher + observer ContextVar target.

    Ownership: one bridge per run; builder binds it, :func:`unbind_run_event_session`
    tears it down. Observer fire is contained by Session.append.
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
        """Commit to Session log, then EventBus.publish (COMPAT dual-write).

        precondition: ``payload`` projects to JSON-serializable data.
        失败语义: Session 校验失败不改日志、不上 EventBus；Session 已提交后
        EventBus 失败上抛，日志保留（append 已 commit）。
        时序: 先置 ``_inflight_payload``，再 ``Session.append``（同步通知
        observer），再按 seq 固化到 ``_payloads``，最后 EventBus 双写。
        """
        event_type, data = _session_event_parts(payload)
        previous = self._inflight_payload
        self._inflight_payload = payload
        try:
            event = self._session.append(event_type, data)
            self._payloads[event.seq] = payload
        finally:
            self._inflight_payload = previous
        return EventBus.default().publish(payload, producer=producer)

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
            ref = EventRef(
                event_id=f"{session.id}:{event.seq}",
                category=event.type,
                trace_id="",
                ts=event.time / 1000.0,
                persisted=False,
                subscriber_count=0,
            )
            callback(payload, ref)

        return self._session.observe(_on_event)


@dataclass(slots=True)
class BoundRunEventSession:
    """Run-local Session binding held on :class:`RunSession` until close."""

    store: Any
    bridge: RunEventSessionBridge
    publish_token: Any
    run_id: str


def bind_run_event_session(ctx: Any, run_id: str) -> BoundRunEventSession | None:
    """Create Session for ``run_id`` and occupy publish/observe slots.

    缺 ``session.store``: 打 structlog warning，返回 None；publishers 保持
    EventBus fallback。在场却 create 失败: 上抛（fail-loud）。
    """
    try:
        store = require_capability(ctx, "session.store")
    except MissingCapabilityError:
        _log.warning(
            "session.store.missing",
            run_id=run_id,
            detail="publishers degrade to EventBus",
        )
        return None

    inner = store.create(run_id)
    if not isinstance(inner, Session):
        raise TypeError(f"session.store.create must return Session, got {type(inner).__name__}")
    bridge = RunEventSessionBridge(inner)
    token = set_publish_session(bridge)
    set_session(bridge)
    return BoundRunEventSession(
        store=store,
        bridge=bridge,
        publish_token=token,
        run_id=run_id,
    )


def unbind_run_event_session(bound: BoundRunEventSession | None) -> None:
    """Reset publish/observe slots and dispose the Session. Idempotent."""
    if bound is None:
        return
    with contextlib.suppress(Exception):
        reset_publish_session(bound.publish_token)
    if current_session() is bound.bridge:
        set_session(None)
    with contextlib.suppress(Exception):
        bound.store.dispose(bound.run_id)
