"""Insertion-ordered storage and effect ownership for scope-aware registries.

1:1 port of ``@deepseek-ai/dsh-scope/store.ts``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Generic, TypeVar

from lca.layer0_infra.dsh_core.scope import ScopeKey, scope_chain_of

V = TypeVar("V")
L = TypeVar("L", bound="ScopeLayer")


class ScopeLayer:
    """One scope's aggregate contribution to a registry."""

    def is_empty(self) -> bool:
        raise NotImplementedError


class NamedEntries(Generic[V]):
    """Insertion-ordered named entries with caller-owned duplicate diagnostics.

    Values are borrowed.  Iterators are live within one non-empty table
    generation; draining the table detaches them from later insertions.
    Each successful insertion returns an idempotent undo.
    """

    def __init__(self, duplicate_error: Callable[[str], Exception]) -> None:
        self._duplicate_error = duplicate_error
        self._data: dict[str, V] = {}

    def insert(self, name: str, value: V) -> Callable[[], None]:
        if name in self._data:
            raise self._duplicate_error(name)
        self._data[name] = value
        data = self._data
        active = True

        def undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            data.pop(name, None)
            if not data and self._data is data:
                self._data = {}

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


class AnonymousEntries(Generic[V]):
    """Insertion-ordered anonymous entries with independent registration identity.

    Equal values remain separate registrations.  Values are borrowed, and
    iterators are live within one non-empty table generation.
    """

    def __init__(self) -> None:
        self._data: dict[object, V] = {}

    def append(self, value: V) -> Callable[[], None]:
        key: object = object()
        self._data[key] = value
        data = self._data
        active = True

        def undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            data.pop(key, None)
            if not data and self._data is data:
                self._data = {}

        return undo

    def values(self) -> Iterator[V]:
        return iter(self._data.values())

    def is_empty(self) -> bool:
        return not self._data


class ScopedLayers(Generic[L]):
    """Own the global and exact-scope layers for one registry.

    Reads never create scoped layers.  Registrations derive both visibility
    and effect ownership from the supplied context.
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
        """Read an existing exact-scope overlay (chain-blind)."""
        if scope is None:
            return None
        return self._scoped.get(scope)

    def chain_layers(self, scope: ScopeKey | None) -> list[L]:
        """Existing overlays along the parent chain, farthest first."""
        layers: list[L] = []
        for key in reversed(scope_chain_of(scope)):
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

        Uses ``ctx.effect(setup, label)`` for teardown ordering.
        """
        scope = _scope_of_ctx(ctx)

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

            if notify:
                self._on_change()
            return dispose

        return ctx.effect(setup, label)


def _scope_of_ctx(ctx: Any) -> ScopeKey | None:
    """Read scope from a PluginContext."""
    from lca.layer0_infra.dsh_core.scope import scope_of

    return scope_of(ctx)
