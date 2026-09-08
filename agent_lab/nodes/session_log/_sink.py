"""Internal Session singleton for the session_log graph nodes.

This file lives INSIDE nodes/session_log/ so it doesn't pollute the
agent_lab package root. All session_log nodes import get_session()
from here; the Session instance is created lazily on first use.

The registry is process-local (single agent loop per process by
default). For multi-session use, configure_session() can be called
externally (e.g. by a test fixture or a runner boot path).
"""

from __future__ import annotations

from typing import Any

_SESSION_SINGLETON: dict[str, Any] = {}
_SINKS_ATTR = "_agent_lab_sinks"  # hung off Session instance


def configure_session(session: Any) -> None:
    """Set the Session used by all session_log nodes in this process."""
    _SESSION_SINGLETON["value"] = session
    if not hasattr(session, _SINKS_ATTR):
        try:
            object.__setattr__(session, _SINKS_ATTR, {})
        except Exception:
            pass


def get_session() -> Any:
    """Return the configured Session; build a default in-memory one if absent."""
    sess = _SESSION_SINGLETON.get("value")
    if sess is not None:
        return sess
    from lca.session.append import Session
    sess = Session(session_id="agent_lab_default")
    _SESSION_SINGLETON["value"] = sess
    try:
        object.__setattr__(sess, _SINKS_ATTR, {})
    except Exception:
        pass
    return sess


# ── Per-Session sink registry (scoped to Session, NOT process-global) ──

def _session_sinks() -> dict:
    """Return the sink-registry dict attached to the current Session."""
    sess = get_session()
    reg = getattr(sess, _SINKS_ATTR, None)
    if reg is None:
        reg = {}
        try:
            object.__setattr__(sess, _SINKS_ATTR, reg)
        except Exception:
            pass
    return reg


def register_session_sink(name: str, sink_instance: Any, flush_fn: Any) -> None:
    """Register a durable sink under ``name`` on the current Session."""
    _session_sinks()[name] = (sink_instance, flush_fn)


def get_session_sink(name: str = "default") -> tuple[Any, Any] | None:
    """Look up a registered sink by name on the current Session."""
    return _session_sinks().get(name)


def unregister_session_sink(name: str) -> None:
    _session_sinks().pop(name, None)


__all__ = [
    "configure_session",
    "get_session",
    "register_session_sink",
    "get_session_sink",
    "unregister_session_sink",
]
