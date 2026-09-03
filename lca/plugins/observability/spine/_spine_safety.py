"""Process-local active spine accessor + safe-append helper (ADR-0169 + ADR-0165.1).

# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine fallback 路径；PR-3~PR-6 已迁 spine_reflector_*，本模块
# 只剩老 exception_emit.py + spine.core._activate_process_local_spine 兜底
# 用。PR-9 全退役时一并删除（rg _spine_safety lca/ = 0 触发）。

Private module. Five reflector modules
(``cognition``, ``runtime``, ``body_llm``, ``agent_spawn``, ``transport_emit``)
each previously maintained their own ``_active_spine`` module-level global,
``set_active_spine`` setter, ``get_active_spine`` getter, and a
``_safe_append(...)`` helper. This module is the single seam.

Public surface (unchanged signature for backwards compatibility):
  * :data:`active_spine` — current :class:`EventSpine` or ``None``.
  * :func:`set_active_spine` — install or clear the binding.
  * :func:`get_active_spine` — read the binding.
  * :func:`safe_append` — append-or-silent-None wrapper.

The five reflectors can keep thin re-export getters if their existing
consumers rely on the module-local symbol; new code should import from
this module directly.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine

_log = logging.getLogger(__name__)

# Process-local state — the single source of truth for which spine
# reflectors append into. Profile boot installs via :func:`set_active_spine`;
# tests install directly. ``None`` means "no spine wired" — helpers
# silently no-op (matches the existing per-module behavior).
_active_spine: EventSpine | None = None


def set_active_spine(spine: EventSpine | None) -> None:
    """Install or clear the process-local active spine.

    Called by profile boot (``kernel_serve`` / ``boot_resolved_profile``)
    at the start of a run. Tests call it directly to wire a capturing
    spine. Passing ``None`` clears the binding.
    """
    global _active_spine
    _active_spine = spine


def get_active_spine() -> EventSpine | None:
    """Return the active spine, or ``None`` if no run is in flight."""
    return _active_spine


def safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Dispatch to the active spine, returning ``None`` when no spine wired.

    Mirrors the prior per-module ``_safe_append`` helpers exactly:
    swallows ``EventRecord`` validation errors (malformed payload,
    unknown execution_point) so a broken helper never blocks the
    caller; logs at WARNING. All other exceptions propagate as FD-1.
    """
    spine = _active_spine
    if spine is None:
        return None
    try:
        return spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
        )
    except ValueError as exc:
        _log.warning(
            "spine_reflector: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


__all__ = [
    "get_active_spine",
    "safe_append",
    "set_active_spine",
]
