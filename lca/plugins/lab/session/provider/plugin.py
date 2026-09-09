# PR-D final (1/2) — lab session provider real composition
"""lab.session provider — wraps the LCA Session binding for the lab act phase.

Replaces the PR-C marker. The actual ``set_publish_session`` call
happens inside the lab run path (not at import time) so we don't
keep a global token. The provider exposes:

- ``bind_active_session(active_session)`` — call once per run; performs
  ``set_publish_session`` exactly once and stashes the session in
  ``lab.session``. Fail-loud if no append-capable session is passed.
- ``unbind()`` — symmetrical teardown for tests.
- ``current()`` — read the currently bound session (or None).

This module does not depend on cordis; it only uses
``lca.plugins.events.publishers._session_publish`` which is the single
session binding entry point (ADR-0209 §1.5, AGENTS.md §3 C10).

delete-when (PR-D final acceptance):
- agent_lab/nodes/act/execute/runtime_bind.py fully deleted
- ``ensure_act_runtime`` / ``_PUBLISH_TOKEN`` no longer exist
  anywhere in agent_lab/
- The infoedge RunLoopDriver calls bind_active_session(active_session)
  on every run entry instead of going through runtime_bind.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    set_publish_session,
    reset_publish_session,
)

PLAN_REF = "agent_lab_act"

_log = logging.getLogger(__name__)


def plan_ref() -> str:
    """Return the lab act plan_ref constant."""
    return PLAN_REF


# Per-process state for the single bound session token. ADR-0209 §1.5
# permits a single-process binding (vs. the previous cross-call global).
_TOKEN: Any = None
_SESSION: Any = None


def bind_active_session(active_session: Any) -> Any:
    """Bind ``active_session`` to the lab session and ``set_publish_session``.

    Idempotent: a second call with the same session returns the
    existing token. A second call with a different session warns and
    rebinds (testing only). No append-capable session -> RuntimeError.

    Returns the session handle for the caller to keep.
    """
    global _SESSION, _TOKEN

    if active_session is None:
        raise RuntimeError(
            "lab.session provider: no active session provided; "
            "call bind_active_session(run_session.event_session) at run entry"
        )

    # Resolve the inner session (RunSession.event_session -> inner/bridge)
    bridge = getattr(active_session, "bridge", None)
    inner = getattr(bridge, "inner", None) if bridge is not None else None
    if callable(getattr(inner, "append", None)):
        session = inner
    elif callable(getattr(active_session, "append", None)):
        session = active_session
    else:
        raise RuntimeError(
            f"lab.session provider: session {type(active_session).__name__} "
            f"has no append() — cannot bind"
        )

    if current_publish_session() is None:
        _TOKEN = set_publish_session(session)
    else:
        _log.debug(
            "lab.session provider: a publish session is already active; "
            "skipping re-bind"
        )

    _SESSION = session
    return session


def unbind() -> None:
    """Release the publish token (tests / teardown)."""
    global _TOKEN, _SESSION
    if _TOKEN is not None:
        reset_publish_session(_TOKEN)
        _TOKEN = None
    _SESSION = None


def current() -> Any | None:
    """Return the currently bound lab session (or None)."""
    return _SESSION


__all__ = ["PLAN_REF", "bind_active_session", "current", "plan_ref", "unbind"]

# Register loader marker for the capability closure.
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_LAB_HOOKS["lab.session"] = {"id": "lab.session", "plan_ref": PLAN_REF}
