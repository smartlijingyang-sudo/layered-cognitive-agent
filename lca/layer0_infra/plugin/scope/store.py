"""Insertion-ordered storage and effect ownership for scope-aware registries.

Python mirror of DSH ``core/scope/store.ts``. Two entry tables plus the
global/scoped layering that tools, skills, and system-prompt registries
share. Values are borrowed; iterators are live within one non-empty table
generation; draining detaches later insertions.

Module is framework-free: it only needs a ``scopeOf(ctx)`` helper and a
context object exposing ``effect()``. Both are provided by
:mod:`lca.layer0_infra.plugin.scope`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Generic, TypeVar, cast

from lca.layer0_infra.plugin.scope.index import ScopeKey, scope_chain_of, scope_of

V = TypeVar("V")
L = TypeVar("L", bound="ScopeLayer")


class ScopeLayer:
    """One scope's aggregate contribution to a registry."""

    def is_empty(self) -> bool:
        raise NotImplementedError


class _EntryValues(Generic[V]):
    def values(self) -> Iterator[V]:  # pragma: no cover
        raise NotImplementedError

    def is_empty(self) -> bool:  # pragma: no cover
        raise NotImplementedError


class NamedEntries(_EntryValues[V], Generic[V]):
    """Insertion-ordered named entries with caller-owned duplicate errors.

    Each successful ``insert`` returns an idempotent undo for that exact
    entry. Values are borrowed.
    """

    def __init__(self, duplicate_error: Callable[[str], Exception]) -> None:
        self._duplicate_error = duplicate_error
        self._data: dict[str, V] = {}

    def insert(self, name: str, value: V) -> Callable[[], None]:
        if name in self._data:
            raise self._duplicate_error(name)
        self._data[name] = value
        active = True

        def undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            self._data.pop(name, None)
            if not self._data and self._data is _data:
                self._data = {}

        _data: dict[str, V] = self._data
        return undo

    def get(self, name: str) -> V | None:
        return self._data.get(name)

    def has(self, name: str) -> bool:
        return name in self._data

    def keys(self) -> Iterator[str]:
        return iter(self._data.keys())

    def entries(self) -> Iterator[tuple[str, V]]:
        return iter(self._data.items())

    def values(self) -> Iterator[V]:
        return iter(self._data.values())

    def is_empty(self) -> bool:
        return not self._data


class AnonymousEntries(_EntryValues[V], Generic[V]):
    """Insertion-ordered anonymous entries with independent identity.

    Equal values remain separate registrations.
    """

    def __init__(self) -> None:
        self._data: dict[object, V] = {}

    def append(self, value: V) -> Callable[[], None]:
        key = object()
        self._data[key] = value
        active = True

        def undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            self._data.pop(key, None)
            if not self._data and self._data is _data:
                self._data = {}

        _data: dict[object, V] = self._data
        return undo

    def values(self) -> Iterator[V]:
        return iter(self._data.values())

    def is_empty(self) -> bool:
        return not self._data


class ScopedLayers(Generic[L]):
    """Own the global and exact-scope layers for one registry.

    Reads never create scoped layers. Registrations derive both visibility
    and effect ownership from the supplied context, collect undo before
    notification, and reclaim only a completely empty aggregate layer.
    """

    def __init__(
        self,
        create_layer: Callable[[ScopeKey | None], L],
        on_change: Callable[[], None],
    ) -> None:
        self._create_layer = create_layer
        self._on_change = on_change
        self._scoped: dict[ScopeKey, L] = {}
        self.global_layer: L = create_layer(None)

    def peek(self, scope: ScopeKey | None) -> L | None:
        """Chain-blind read of one scope's own overlay; never creates."""
        if scope is None:
            return None
        return self._scoped.get(scope)

    def chain_layers(self, scope: ScopeKey | None) -> list[L]:
        """Existing overlays along the parent chain, nearest scope last."""
        layers: list[L] = []
        for key in _chain_of(scope):
            layer = self._scoped.get(key)
            if layer is not None:
                layers.append(layer)
        return layers

    def merge(
        self,
        scope: ScopeKey | None,
        pick: Callable[[L], NamedEntries[Any]],
    ) -> dict[str, Any]:
        """Global named entries followed by scope-chain shadows, nearest wins."""
        merged = dict(pick(self.global_layer).entries())
        for layer in self.chain_layers(scope):
            for name, value in pick(layer).entries():
                merged[name] = value
        return merged

    def effect(
        self,
        ctx: Any,
        action: Callable[[L], Callable[[], None]],
        *,
        label: str,
        notify: bool = True,
    ) -> Callable[[], None]:
        """Attach one synchronous layer mutation to its registration context.

        The scope is derived from *ctx*; the returned disposer is the exact
        one returned by ``ctx.effect()``, preserving teardown order.
        """
        scope = scope_of(ctx)

        def setup() -> Callable[[], None]:
            layer: L
            created = False
            if scope is None:
                layer = self.global_layer
            else:
                existing = self._scoped.get(scope)
                if existing is None:
                    layer = self._create_layer(scope)
                    self._scoped[scope] = layer
                    created = True
                else:
                    layer = existing

            try:
                undo = action(layer)
            except BaseException:
                if scope is not None and created and layer.is_empty():
                    self._scoped.pop(scope, None)
                raise

            def dispose() -> None:
                undo()
                if scope is not None and layer.is_empty():
                    self._scoped.pop(scope, None)
                if notify:
                    self._on_change()

            return dispose

        disposer = ctx.effect(setup, label)
        return cast("Callable[[], None]", disposer)


def _chain_of(scope: ScopeKey | None) -> list[ScopeKey]:
    """Parent chain, nearest scope last (mirrors ``scopeChainOf``)."""
    if scope is None:
        return []
    return list(reversed(scope_chain_of(scope)))
