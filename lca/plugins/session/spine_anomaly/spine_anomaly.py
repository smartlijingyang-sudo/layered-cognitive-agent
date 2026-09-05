"""Session observer for spine anomaly detection (ADR-0186 wave 3).

``AnomalyDetector.on_event`` runs on committed Session spine events via
``Session.observe`` — not via ``EmitPipeline.emit`` when a run-bound
Session hook is active.

# COMPAT(owner: ADR-0186 wave-3, from: EmitPipeline.emit → anomaly.on_event,
#         to: Session observer + hook-less EmitPipeline fallback,
#         delete_when: rg 'self\\._anomaly\\.on_event' lca/plugins/observability/spine/emit_pipeline.py = 0,
#         forbidden_new_usage: EventSpine.subscribe(anomaly) in production boot)
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

import structlog

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.session.runtime.spine_event_projection import session_event_to_event_record
from lca_kernel.events.session import SessionEvent, SessionProtocol

_log = structlog.get_logger(__name__)

_active_anomaly_detector: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "lca_active_anomaly_detector",
    default=None,
)

__all__ = [
    "get_active_anomaly_detector",
    "register_spine_anomaly_to_store",
    "reset_active_anomaly_detector",
    "set_active_anomaly_detector",
    "setup",
]


def set_active_anomaly_detector(detector: Any | None) -> Any | None:
    previous = _active_anomaly_detector.get()
    _active_anomaly_detector.set(detector)
    return previous


def reset_active_anomaly_detector(token: contextvars.Token[Any | None]) -> None:
    _active_anomaly_detector.reset(token)


def get_active_anomaly_detector() -> Any | None:
    return _active_anomaly_detector.get()


class _SpineAnomalyObserver:
    __slots__ = ("_detector",)

    def __init__(self, detector: Any) -> None:
        self._detector = detector

    def __call__(self, session: SessionProtocol, event: SessionEvent) -> None:
        record = session_event_to_event_record(session, event)
        if record is None:
            return
        try:
            self._detector.on_event(record)
        except Exception:
            _log.warning(
                "session.spine_anomaly.observer_failed",
                session_id=session.id,
                seq=event.seq,
                event_type=event.type,
                exc_info=True,
            )


def register_spine_anomaly_to_store(store: Any, detector: Any) -> None:
    """Attach anomaly observer to live sessions and future creates/restores."""
    observer = _SpineAnomalyObserver(detector)

    def _attach(session: Any) -> None:
        try:
            session.observe(observer)
        except Exception:
            _log.warning(
                "session.spine_anomaly.attach_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )

    for session in getattr(store, "list", lambda: ())():
        _attach(session)
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)
    hook(_attach)


@plugin(
    id="lca.plugins.session.spine_anomaly",
    provides=("session.spine_anomaly",),
    requires=("session.store", "deriver.anomaly"),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Spine anomaly Session observer — runs AnomalyDetector on committed "
        "spine-shaped Session events (I15/I16; ADR-0186 wave 3)."
    ),
    test_suite="tests/plugins/session/test_spine_anomaly_observer.py",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    detector = ctx.require("deriver.anomaly")
    store = ctx.require("session.store")
    set_active_anomaly_detector(detector)
    register_spine_anomaly_to_store(store, detector)
    ctx.provide("session.spine_anomaly", detector)
    logging.getLogger(__name__).debug("session.spine_anomaly: wired to session.store")
