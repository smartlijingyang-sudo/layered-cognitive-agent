"""Public seam for per-task event-bridge binding (RA-044).

Converges the bind/reset ritual previously inlined (twice, with inline
imports of private modules) in
``RunLifecycleCoordinator.execute``/``.resume``: a run's event bridge is
bound as both the active publish session and the observe session for the
duration of one task, then reset. The private ``_session_observe`` /
``publishers._session_publish`` modules stay private — this module is
their public face for the carrier lifecycle.

Why explicit bind/unbind instead of a context manager: both call sites
bind before a large ``try`` block and reset inside its ``finally``
*before* ``emit_kernel_run_stop`` — a context manager would invert that
order. The pairing still lives here, once.
"""

from __future__ import annotations

import contextvars
from typing import Any

from lca.plugins.events._session_observe import set_session
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)


def bind_event_bridge(
    bridge: Any | None,
) -> contextvars.Token[Any] | None:
    """Bind ``bridge`` as the active publish + observe session.

    Returns an opaque token for :func:`unbind_event_bridge`, or ``None``
    when ``bridge`` is ``None`` (callers keep their existing None-guard
    shape; the token is only ever non-None when a bind happened).
    """
    if bridge is None:
        return None
    token = set_publish_session(bridge)
    set_session(bridge)
    return token


def unbind_event_bridge(token: contextvars.Token[Any] | None) -> None:
    """Reset a binding created by :func:`bind_event_bridge`. None-safe."""
    if token is None:
        return
    reset_publish_session(token)
    set_session(None)


__all__ = ["bind_event_bridge", "unbind_event_bridge"]
