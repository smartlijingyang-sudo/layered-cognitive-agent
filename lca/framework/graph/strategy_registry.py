"""Strategy registry — maps :class:`BindingKind` to :class:`NodeStrategy`.

The registry is a flat dict, populated by module-level
:func:`register_strategy` calls in the strategy modules. Adding a
binding kind is a four-step change:

1. Add the enum value to :class:`lca.contracts.protocols.graph.binding.BindingKind`.
2. Write a :class:`NodeStrategy` subclass in this package.
3. Call :func:`register_strategy` once at module load time.
4. Write a test that resolves the kind via :func:`default_strategy_registry`.

No global lookup at runtime cost: the registry is read once per visit
to fetch the strategy object, then ``execute`` is called directly.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.strategy import NodeStrategy


class PhaseExecutorLookup(Protocol):
    """Strategy-side seam to resolve an executor for one binding + node.

    The kernel does not know how to look up an executor. The strategy
    receives a :class:`PhaseExecutorLookup` callable and uses it to
    fetch the right executor for the current node. Implementations live
    in the host (typically a Cordis-injected closure in tests, or the
    production ``CapabilityKeyResolver`` in deployment).
    """

    def __call__(self, *, binding: BindingKind, node_id: str, region: str | None) -> Any: ...


class StrategyRegistry:
    """Mutable registry. Built once at startup; read-only at runtime."""

    def __init__(self) -> None:
        self._strategies: dict[BindingKind, NodeStrategy] = {}

    def register(self, strategy: NodeStrategy) -> None:
        if strategy.kind in self._strategies:
            raise ValueError(
                f"binding {strategy.kind.value!r} already registered; "
                "one strategy per binding is the rule"
            )
        self._strategies[strategy.kind] = strategy

    def resolve(self, kind: BindingKind) -> NodeStrategy:
        if kind not in self._strategies:
            raise KeyError(
                f"no strategy registered for binding {kind.value!r}; "
                f"available: {sorted(k.value for k in self._strategies)}"
            )
        return self._strategies[kind]

    def kinds(self) -> tuple[BindingKind, ...]:
        return tuple(sorted(self._strategies, key=lambda k: k.value))


_DEFAULT = StrategyRegistry()


def register_strategy(strategy: NodeStrategy) -> NodeStrategy:
    """Register ``strategy`` in the default registry. Returns the strategy."""
    _DEFAULT.register(strategy)
    return strategy


def default_strategy_registry() -> StrategyRegistry:
    """Return the default registry, populated by side-effect at import time."""
    return _DEFAULT


def resolve_executor(
    lookup: PhaseExecutorLookup | None,
    *,
    binding: BindingKind,
    node_id: str,
    region: str | None = None,
) -> Any:
    """Helper: invoke a :class ``PhaseExecutorLookup`` or raise."""
    if lookup is None:
        raise RuntimeError(
            f"no executor lookup registered; cannot resolve binding={binding.value!r} "
            f"node_id={node_id!r}"
        )
    return lookup(binding=binding, node_id=node_id, region=region)


__all__ = [
    "PhaseExecutorLookup",
    "StrategyRegistry",
    "default_strategy_registry",
    "register_strategy",
    "resolve_executor",
]