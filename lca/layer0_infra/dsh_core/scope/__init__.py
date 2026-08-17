"""Scope primitives — per-agent scoped context and event carriers.

1:1 port of ``@deepseek-ai/dsh-scope/index.ts``.

- :func:`create_scope` — fork a child context tagged with *key*
- :func:`scope_of` — read the nearest inherited scope key
- :func:`scope_target` — build an event carrier that filters dispatch
- :func:`bind_scope_parent` / :func:`scope_chain_of` — parent chain
"""

from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

# ---------------------------------------------------------------------------
# ScopeKey — opaque identity-compared scope key (TS: ``type ScopeKey = object``)
# ---------------------------------------------------------------------------

ScopeKey = Any

K = TypeVar("K", bound=ScopeKey)
T = TypeVar("T")

# ---------------------------------------------------------------------------
# Parent chain (WeakMap equivalent via dict with id-based keys)
# ---------------------------------------------------------------------------

_scope_parents: dict[int, tuple[ScopeKey, ScopeKey]] = {}
"""Maps id(key) -> (key, parent).  We store the key itself to prevent GC
of the mapping while the key is alive."""


class ScopeParentBinding:
    """Privileged handle to move one scope key's parent link.

    Only the original binder receives this; everyone else gets an error
    if they try to re-bind.
    """

    __slots__ = ("_key", "_key_id")

    def __init__(self, key: ScopeKey) -> None:
        self._key_id = id(key)
        self._key = key

    def rebind(self, parent: ScopeKey) -> None:
        """Re-link the bound key to a different parent."""
        _link_scope_parent(self._key, parent)


def _link_scope_parent(key: ScopeKey, parent: ScopeKey) -> None:
    """Cycle-checked write shared by bind and rebind."""
    cursor: ScopeKey | None = parent
    while cursor is not None:
        if cursor is key:
            raise ValueError("dsh-scope: scope parent link would form a cycle")
        cursor = _scope_parents.get(id(cursor), (None, None))[1]
    _scope_parents[id(key)] = (key, parent)


def bind_scope_parent(key: ScopeKey, parent: ScopeKey) -> ScopeParentBinding:
    """Bind *parent* as *key*'s enclosing scope, once.

    Returns the :class:`ScopeParentBinding` that alone may re-link this key.
    """
    if id(key) in _scope_parents:
        raise ValueError(
            "dsh-scope: scope key is already bound to a parent; "
            "re-linking requires the binding returned by the original bind",
        )
    _link_scope_parent(key, parent)
    return ScopeParentBinding(key)


def scope_parent_of(key: ScopeKey) -> ScopeKey | None:
    """Read one key's enclosing scope."""
    entry = _scope_parents.get(id(key))
    return entry[1] if entry is not None else None


def scope_chain_of(key: ScopeKey | None) -> list[ScopeKey]:
    """The chain from *key* to its root ancestor.

    Returns nearest-first: ``[key, parent, grandparent, ...]``.
    """
    chain: list[ScopeKey] = []
    cursor = key
    seen: set[int] = set()
    while cursor is not None:
        cid = id(cursor)
        if cid in seen:
            break  # safety against cycles from external mutation
        seen.add(cid)
        chain.append(cursor)
        cursor = scope_parent_of(cursor)
    return chain


# ---------------------------------------------------------------------------
# Scoped<T> — routing-only event carrier
# ---------------------------------------------------------------------------


@runtime_checkable
class ScopeCarrier(Protocol):
    """A routing-only event receiver built by :func:`scope_target`."""

    @property
    def scope_key(self) -> ScopeKey: ...


# WeakMap-like storage for carrier -> key mapping
_carrier_keys: dict[int, ScopeKey | None] = {}
_carrier_ids: set[int] = set()


# ---------------------------------------------------------------------------
# Scope — minted registration scope with disposal
# ---------------------------------------------------------------------------


class Scope:
    """A minted registration scope and its disposal boundaries."""

    __slots__ = ("_dispose_future", "_raw_dispose", "ctx")

    def __init__(self, ctx: Any, raw_dispose: Any) -> None:
        self.ctx = ctx
        self._raw_dispose = raw_dispose
        self._dispose_future: Any = None

    @property
    def raw_dispose(self) -> Any:
        return self._raw_dispose

    async def dispose(self) -> None:
        """Dispose every scope-owned registration; racing calls await same completion."""
        if self._dispose_future is not None:
            await self._dispose_future
            return
        import asyncio

        self._dispose_future = asyncio.ensure_future(_call_dispose(self._raw_dispose))
        await self._dispose_future


async def _call_dispose(disposer: Any) -> None:
    import inspect

    if inspect.isawaitable(disposer):
        await disposer
    elif callable(disposer):
        result = disposer()
        if inspect.isawaitable(result):
            await result


# ---------------------------------------------------------------------------
# create_scope
# ---------------------------------------------------------------------------


def create_scope(ctx: Any, key: ScopeKey, *, parent: ScopeKey | None = None) -> Scope:
    """Mint a scope under *ctx*.

    The scoped context inherits the minting plugin's dependency API and
    owns every registration made through it.
    """
    if parent is not None:
        bind_scope_parent(key, parent)
    child = ctx.child(key=str(getattr(key, "name", id(key))), scope=key)

    # Build a disposer that delegates to the child's handle if available
    def _dispose() -> None:
        handle = getattr(child, "_handle", None)
        if handle is not None:
            from lca.layer0_infra.plugin.kernel._lifecycle import deactivate

            deactivate(handle)

    return Scope(child, _dispose)


# ---------------------------------------------------------------------------
# scope_of
# ---------------------------------------------------------------------------


def scope_of(ctx: Any) -> ScopeKey | None:
    """Read the nearest scope tag inherited by a context."""
    # Direct tag
    scope = getattr(ctx, "scope", None)
    if scope is not None:
        return scope
    tag = getattr(ctx, "_lca_scope", None)
    if tag is not None:
        return tag
    # Inherit from parent
    parent = getattr(ctx, "parent", None)
    if parent is not None:
        return scope_of(parent)
    return None


# ---------------------------------------------------------------------------
# scope_target — build an event carrier with scope filter
# ---------------------------------------------------------------------------


class _ScopeTargetCarrier:
    """Event carrier built by :func:`scope_target`.

    Preserves the base filter, admits untagged listeners globally, and
    admits tagged listeners for a matching key or any of its ancestors.
    """

    __slots__ = ("_base", "_key", "scope_key")

    def __init__(self, base: Any, key: ScopeKey | None) -> None:
        self._base = base
        self._key = key
        self.scope_key = key

    def accepts(self, ctx: Any) -> bool:
        """Check if *ctx* is within this carrier's scope.

        - If base has a filter, it must pass first.
        - If ctx has no scope tag → admit (global/untagged).
        - Walk from key toward root; if any ancestor matches ctx's tag → admit.
        """
        # Base filter
        base_filter = getattr(self._base, "_scope_filter", None)
        if base_filter is not None and not base_filter(ctx):
            return False
        tag = scope_of(ctx)
        if tag is None:
            return True  # untagged context → global listener
        # Walk from key toward root
        cursor: ScopeKey | None = self._key
        while cursor is not None:
            if cursor is tag:
                return True
            cursor = scope_parent_of(cursor)
        return False


def scope_target(base: T, key: ScopeKey | None) -> Any:
    """Build an opaque receiver that preserves the base filter.

    Admits untagged listeners globally, and admits tagged listeners for
    a matching key or any of its ancestors.  Events flow up the chain,
    never down.
    """
    carrier = _ScopeTargetCarrier(base, key)
    _carrier_keys[id(carrier)] = key
    _carrier_ids.add(id(carrier))
    return carrier


def is_scope_carrier(value: object) -> bool:
    """Test whether a value is a scope carrier."""
    return id(value) in _carrier_ids


def carrier_key_of(value: object) -> ScopeKey | None:
    """Read a carrier's routing key."""
    if not is_scope_carrier(value):
        return None
    return _carrier_keys.get(id(value))
