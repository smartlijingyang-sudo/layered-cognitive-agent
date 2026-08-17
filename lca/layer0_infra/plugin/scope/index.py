"""Scope primitives — per-agent scoped context and event carriers.

Python mirror of DSH ``core/scope/index.ts``:

- ``createScope(ctx, key)`` — fork a child context tagged with *key*; the
  child owns its own overlay and all registrations made on it land in the
  scope's layer.
- ``scopeOf(ctx)`` — read the nearest inherited scope key.
- ``scopeTarget(base, key)`` — build an event carrier that filters dispatch
  to listeners registered on *key* or an ancestor scope.
- ``bind_scope_parent`` / ``scope_chain_of`` — parent chain traversal,
  nearest scope last for layering.
"""

from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar

# Opaque scope key. Any hashable object identity works; the parent link is
# stored in a WeakKeyDictionary so scope keys need no ``__dict__`` and are
# reclaimed with their owners.
ScopeKey = Any

K = TypeVar("K", bound=ScopeKey)

_SCOPE_PARENT = "_lca_scope_parent"

_scope_parents: dict[object, ScopeKey] = {}


class ScopeCarrier(Protocol):
    """A value that routes an event to a scope's listeners."""

    @property
    def scope_key(self) -> ScopeKey: ...


class _ScopedCtx(Generic[K]):
    """A child context carrying a scope tag.

    The underlying object must expose ``child(key=..., values=...)`` for
    forking (the LCA ``PluginContext`` does). Registrations and events
    created on this context inherit the tag.
    """

    __slots__ = ("_ctx", "_key")

    def __init__(self, ctx: Any, key: K) -> None:
        self._ctx = ctx
        self._key = key

    @property
    def ctx(self) -> Any:
        return self._ctx

    @property
    def key(self) -> K:
        return self._key

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)

    def child(self, *, key: str, values: dict[str, Any] | None = None) -> Any:
        return self._ctx.child(key=key, values=values)


def bind_scope_parent(key: ScopeKey, parent: ScopeKey) -> ScopeKey:
    """Bind a parent link. Returns *key*. Rebinding is an error."""
    existing = _scope_parents.get(key)
    if existing is not None and existing is not parent:
        raise ValueError("scope parent already bound")
    _scope_parents[key] = parent
    return key


def scope_parent_of(key: ScopeKey) -> ScopeKey | None:
    return _scope_parents.get(key)


def scope_chain_of(key: ScopeKey) -> list[ScopeKey]:
    """Scope chain, self first, nearest parent last."""
    chain: list[ScopeKey] = []
    current: ScopeKey = key
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = _scope_parents.get(current)
    return chain


def create_scope(ctx: Any, key: ScopeKey) -> _ScopedCtx:
    """Fork a child context tagged with *key*.

    Returns a wrapper whose ``ctx`` is the forked context. Call
    ``dispose()`` on the wrapper to tear it down (delegates to the child's
    owner if it exposes ``dispose``; otherwise the child is a plain overlay).
    """
    child = ctx.child(key=str(getattr(key, "name", id(key))), scope=key)
    return _ScopedCtx(child, key)


def scope_of(ctx: Any) -> ScopeKey | None:
    """Read the nearest inherited scope key from *ctx*."""
    scope = getattr(ctx, "scope", None)
    if scope is not None:
        return scope
    tag = getattr(ctx, "_lca_scope", None)
    if tag is not None:
        return tag
    parent = getattr(ctx, "parent", None)
    if parent is not None:
        return scope_of(parent)
    return None


def scope_target(base: Any, key: ScopeKey) -> ScopeCarrier:
    """Build an event carrier scoped to *key*.

    The carrier carries the scope filter; the event bus consults
    ``scope_key`` when routing so listeners registered on *key* or an
    ancestor receive the dispatch, and listeners outside the chain do not.
    """
    carrier = _ScopeTargetCarrier(base, key)
    return carrier


class _ScopeTargetCarrier:
    __slots__ = ("base", "scope_key")

    def __init__(self, base: Any, key: ScopeKey) -> None:
        self.base = base
        self.scope_key = key
