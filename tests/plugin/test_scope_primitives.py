"""Scope primitives and layered registries — DSH ``core/scope`` mirror tests."""

from __future__ import annotations

from typing import Any

import pytest

from lca.layer0_infra.plugin.scope.index import (
    bind_scope_parent,
    create_scope,
    scope_chain_of,
    scope_of,
    scope_parent_of,
    scope_target,
)
from lca.layer0_infra.plugin.scope.store import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)


class _FakeCtx:
    """Minimal context: child forking + scope tag + effect registration."""

    def __init__(self) -> None:
        self.parent: _FakeCtx | None = None
        self._scope: Any = None
        self.effects: list[Any] = []

    def child(
        self, *, key: str, values: dict[str, Any] | None = None, scope: Any = None
    ) -> _FakeCtx:
        child = _FakeCtx()
        child.parent = self
        child._scope = scope if scope is not None else self._scope
        return child

    @property
    def scope(self) -> Any:
        return (
            self._scope if self._scope is not None else (self.parent.scope if self.parent else None)
        )

    def effect(self, setup: Any, label: str) -> Any:
        result = setup()
        self.effects.append((result, label))
        return result


class TestScopeIndex:
    def test_create_scope_tags_child(self) -> None:
        ctx = _FakeCtx()
        key = object()
        scoped = create_scope(ctx, key)
        assert scope_of(scoped.ctx) is key

    def test_scope_of_inherits_from_parent(self) -> None:
        ctx = _FakeCtx()
        key = object()
        scoped = create_scope(ctx, key)
        grandchild = scoped.ctx.child(key="run")
        assert scope_of(grandchild) is key

    def test_scope_parent_chain(self) -> None:
        parent, child = object(), object()
        bind_scope_parent(child, parent)
        assert scope_parent_of(child) is parent
        assert scope_chain_of(child) == [child, parent]

    def test_scope_chain_of_untagged_is_singleton(self) -> None:
        key = object()
        assert scope_chain_of(key) == [key]

    def test_rebind_parent_raises(self) -> None:
        a, b, c = object(), object(), object()
        bind_scope_parent(a, b)
        with pytest.raises(ValueError):
            bind_scope_parent(a, c)

    def test_scope_target_carries_key(self) -> None:
        key = object()
        carrier = scope_target(object(), key)
        assert carrier.scope_key is key


class TestNamedEntries:
    def test_insert_get_undo(self) -> None:
        table = NamedEntries[int](lambda n: KeyError(n))
        undo = table.insert("a", 1)
        assert table.get("a") == 1
        undo()
        assert table.get("a") is None
        assert table.is_empty()

    def test_undo_is_idempotent(self) -> None:
        table = NamedEntries[int](lambda n: KeyError(n))
        undo = table.insert("a", 1)
        undo()
        undo()
        assert table.is_empty()

    def test_duplicate_raises(self) -> None:
        table = NamedEntries[int](lambda n: KeyError(n))
        table.insert("a", 1)
        with pytest.raises(KeyError):
            table.insert("a", 2)


class TestAnonymousEntries:
    def test_append_undo(self) -> None:
        table = AnonymousEntries[int]()
        undo = table.append(1)
        assert list(table.values()) == [1]
        undo()
        assert table.is_empty()

    def test_equal_values_remain_separate(self) -> None:
        table = AnonymousEntries[int]()
        u1 = table.append(7)
        table.append(7)
        assert list(table.values()) == [7, 7]
        u1()
        assert list(table.values()) == [7]


class _Layer(ScopeLayer):
    def __init__(self) -> None:
        self.named = NamedEntries[int](lambda n: KeyError(n))
        self.anon = AnonymousEntries[int]()

    def is_empty(self) -> bool:
        return self.named.is_empty() and self.anon.is_empty()


class TestScopedLayers:
    def test_global_merge(self) -> None:
        layers = ScopedLayers[_Layer](lambda _: _Layer(), lambda: None)
        layers.global_layer.named.insert("a", 1)
        merged = layers.merge(None, lambda layer: layer.named)
        assert merged == {"a": 1}

    def test_scoped_shadow_wins(self) -> None:
        layers = ScopedLayers[_Layer](lambda _: _Layer(), lambda: None)
        layers.global_layer.named.insert("a", 1)
        scope = object()
        ctx = _FakeCtx()
        scoped = create_scope(ctx, scope)

        def register(layer: _Layer) -> Any:
            return layer.named.insert("a", 2)

        layers.effect(scoped.ctx, register, label="test")
        merged = layers.merge(scope, lambda layer: layer.named)
        assert merged["a"] == 2

    def test_effect_dispose_removes_layer(self) -> None:
        layers = ScopedLayers[_Layer](lambda _: _Layer(), lambda: None)
        scope = object()
        ctx = _FakeCtx()
        scoped = create_scope(ctx, scope)
        disposer = layers.effect(scoped.ctx, lambda layer: layer.named.insert("a", 1), label="test")
        assert layers.peek(scope) is not None
        disposer()
        assert layers.peek(scope) is None

    def test_chain_layers_nearest_last(self) -> None:
        parent, child = object(), object()
        bind_scope_parent(child, parent)
        layers = ScopedLayers[_Layer](lambda _: _Layer(), lambda: None)
        layers.global_layer.named.insert("x", "global")
        for scope, value in ((parent, "parent"), (child, "child")):
            ctx = _FakeCtx()
            layers.effect(
                create_scope(ctx, scope).ctx,
                lambda layer, v=value: layer.named.insert("x", v),
                label="t",
            )
        merged = layers.merge(child, lambda layer: layer.named)
        assert merged["x"] == "child"
