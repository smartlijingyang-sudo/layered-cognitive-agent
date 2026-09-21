"""Ambient plane bindings for one execution context.

One concept: which plane is bound to the current turn. A ``ContextVar``
carries ``PlaneBindings`` across tool construction and prompt assembly so a
call site does not need to thread the plane through every signature.

Authorization is a different concept and lives in ``runtime_plane.access``;
path algebra lives in ``runtime_plane.paths``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from lca.contracts.models.core.state.plane import PlaneBindings, PlaneRef

_bindings: ContextVar[PlaneBindings | None] = ContextVar("plane_bindings", default=None)


@contextmanager
def plane_bindings_scope(bindings: PlaneBindings) -> Iterator[PlaneBindings]:
    token = _bindings.set(bindings)
    try:
        yield bindings
    finally:
        _bindings.reset(token)


def current_bindings() -> PlaneBindings | None:
    return _bindings.get()


def current_primary() -> PlaneRef | None:
    bound = _bindings.get()
    return None if bound is None else bound.primary


__all__ = ["current_bindings", "current_primary", "plane_bindings_scope"]
