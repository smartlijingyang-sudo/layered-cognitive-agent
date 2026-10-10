"""Process-local spine / EmitPipeline accessors —— seam 读侧 SSOT.

本模块原位于 ``lca.harness.declarative.compile.instrument.accessors``；
ADR-0096 seam 读侧补完后下沉 ``lca.contracts``，harness / plugins /
infrastructure 均经此解析 active spine，不再直引 ``lca.harness``
(包契约 pin)。旧路径保留为兼容 re-export.

Process-local spine / EmitPipeline accessors for ``wrap_instrument``.

``lca.harness`` must not statically import ``lca.plugins``, so the
pipeline is reached duck-typed via a pluggable accessor rather than by
importing :class:`EmitPipeline`. The spine plugins register against
these accessors at boot; unit tests leave them unwired and the wrapper
falls back to ``None``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from lca.contracts.observability import EventSpine

log = logging.getLogger(__name__)

_active_spine_getter: Callable[[], EventSpine | None] | None = None
_active_pipeline_getter: Callable[[], Any] | None = None


def set_active_spine_accessor(
    getter: Callable[[], EventSpine | None] | None,
) -> Callable[[], EventSpine | None] | None:
    """Install a process-local spine accessor used by :func:`wrap_instrument`.

    Returns the previous accessor so callers can restore it (typically
    tests using a ``monkeypatch`` style scope).
    """
    global _active_spine_getter
    previous = _active_spine_getter
    _active_spine_getter = getter
    return previous


def set_active_pipeline_accessor(
    getter: Callable[[], Any] | None,
) -> Callable[[], Any] | None:
    """Install a process-local EmitPipeline accessor for :func:`wrap_instrument`.

    When a pipeline is installed, ``wrap_instrument`` routes every
    emission through ``EmitPipeline.emit(...)`` so enabled
    ``FieldProducer`` plugins contribute their keys to
    ``EventRecord.payload``. With no pipeline installed, the wrapper
    falls back to the direct ``EventSpine.append`` path so PR-4
    assembler contracts still hold under unit tests.

    Returns the previous accessor so callers can restore it.
    """
    global _active_pipeline_getter
    previous = _active_pipeline_getter
    _active_pipeline_getter = getter
    return previous


def _resolve_spine() -> EventSpine | None:
    if _active_spine_getter is None:
        return None
    try:
        return _active_spine_getter()
    except Exception as exc:  # pragma: no cover — defensive only
        log.warning("wrap_instrument: spine accessor raised %r", exc)
        return None


def _resolve_pipeline() -> Any:
    """Return the active ``EmitPipeline`` (structural Protocol), or ``None``.

    The protocol is structural: we never import :class:`EmitPipeline`
    here because ``lca.harness`` must not statically import
    ``lca.plugins`` (plugin tree is an optional boot-time layer). The
    pipeline accessor is registered by the boot path via
    :func:`set_active_pipeline_accessor` and the wrapper calls the
    duck-typed ``emit(...)`` method.
    """
    if _active_pipeline_getter is None:
        return None
    try:
        return _active_pipeline_getter()
    except Exception as exc:  # pragma: no cover — defensive only
        log.warning("wrap_instrument: pipeline accessor raised %r", exc)
        return None


def resolve_active_pipeline() -> Any:
    """Return the installed ``emit_pipeline`` or ``None`` when unwired.

    Public counterpart of :func:`_resolve_pipeline` for the
    ``ctx_effect`` / ``ctx_intercept`` wrap plugins, which must resolve
    the same pipeline through the same seam rather than reach into this
    module's private helpers or install a second accessor.
    """
    return _resolve_pipeline()


def resolve_active_spine() -> EventSpine | None:
    """Return the installed ``EventSpine`` or ``None`` when unwired.

    Public counterpart of :func:`_resolve_spine`; see
    :func:`resolve_active_pipeline` for why the wrap plugins need it.
    """
    return _resolve_spine()


__all__ = [
    "resolve_active_pipeline",
    "resolve_active_spine",
    "set_active_pipeline_accessor",
    "set_active_spine_accessor",
]
