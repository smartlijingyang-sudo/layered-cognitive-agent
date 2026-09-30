"""Tests for the generic in-memory handler registry factory.

The Action/Effect/Delta handler seams share one neutral container: unique
ownership keyed by operation, ``register``/``resolve``, and a stable snapshot.
``make_inmemory_registry`` materializes a protocol-satisfying registry class
for each seam without duplicating the container behavior.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.act.action.handler import ActionHandlerRegistry
from lca.contracts.protocols.act.effect.handler import EffectHandlerRegistry
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.infrastructure.handler.registry import make_inmemory_registry


def test_factory_returns_class_satisfying_action_protocol() -> None:
    """The factory-built registry satisfies the ActionHandlerRegistry protocol."""

    registry_class = make_inmemory_registry("action handler", ActionHandlerRegistry)
    registry = registry_class()
    assert isinstance(registry, ActionHandlerRegistry)

    handler = object()
    registry.register("respond", handler)
    assert registry.resolve("respond") is handler
    assert registry.resolve("unknown") is None
    assert registry.registered() == ("respond",)


def test_factory_returns_class_satisfying_effect_protocol() -> None:
    """The factory-built registry satisfies the EffectHandlerRegistry protocol."""

    registry_class = make_inmemory_registry("effect handler", EffectHandlerRegistry)
    registry = registry_class()
    assert isinstance(registry, EffectHandlerRegistry)

    handler = object()
    registry.register("body.act", handler)
    assert registry.resolve("body.act") is handler
    assert registry.resolve("unknown") is None
    assert registry.registered_effect_operations() == ("body.act",)


def test_factory_returns_class_satisfying_delta_protocol() -> None:
    """The factory-built registry satisfies the DeltaHandlerRegistry protocol."""

    registry_class = make_inmemory_registry("delta handler", DeltaHandlerRegistry)
    registry = registry_class()
    assert isinstance(registry, DeltaHandlerRegistry)

    handler = object()
    registry.register("step", handler)
    assert registry.resolve("step") is handler
    assert registry.resolve("unknown") is None
    assert registry.registered_delta_operations() == ("step",)


def test_factory_registry_rejects_duplicate_owner() -> None:
    """A second owner for the same operation must fail at the seam."""

    registry_class = make_inmemory_registry("delta handler", DeltaHandlerRegistry)
    registry = registry_class()
    first = object()
    registry.register("step", first)
    with pytest.raises(KeyError, match="delta handler: operation 'step' already registered"):
        registry.register("step", object())
    assert registry.resolve("step") is first


def test_factory_registry_rejects_invalid_operation() -> None:
    """Empty and non-string operations must be rejected before registration."""

    registry_class = make_inmemory_registry("action handler", ActionHandlerRegistry)
    registry = registry_class()
    with pytest.raises(ValueError, match="action handler: operation must be a non-empty string"):
        registry.register("", object())
    with pytest.raises(ValueError, match="action handler: operation must be a non-empty string"):
        registry.register("   ", object())
    with pytest.raises(ValueError, match="action handler: operation must be a non-empty string"):
        registry.register(7, object())  # type: ignore[arg-type]


def test_factory_result_supports_subclassing() -> None:
    """The factory result remains a regular class that supports subclassing."""

    registry_class = make_inmemory_registry("effect handler", EffectHandlerRegistry)

    class DefaultEffectHandlerRegistry(registry_class):
        def __init__(self) -> None:
            super().__init__()
            self.register("body.act", object())

    registry = DefaultEffectHandlerRegistry()
    assert isinstance(registry, EffectHandlerRegistry)
    assert registry.resolve("body.act") is not None
