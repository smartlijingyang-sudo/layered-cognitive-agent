"""SubgraphRuntime abstraction + PluginContext-backed default implementation.

The framework layer owns the protocol; the plugin layer owns the
binding model. ``PluginContextBackedRuntime`` is the standard seam
that resolves capabilities via :meth:`PluginContext.require`, so the
framework never invents objects of its own — every capability is
sourced from a :func:`@plugin`-registered binding, and a missing
binding fails at :meth:`SubgraphRuntime.resolve` time rather than
silently fabricating a default.

Per ADR-0219 §6 / plan §3.2 / §13.3:

- :class:`SubgraphRuntime` (Protocol) is the seam between the framework
  layer and the runtime layer that owns concrete capability instances.
- :class:`PluginContextBackedRuntime` is the default implementation,
  sourced from a :class:`PluginContext`. It walks ``ctx.require`` for
  every ``resolve(capability)`` call and a ``f"{region}::{factory}"``
  composite key for ``resolve_factory``.
- Inner subgraph node plugins read ``context.runtime.<capability>``;
  the framework's :class:`NodeRuntimeView` translates that into a
  ``runtime.resolve(capability)`` call, which routes here.

Profile / bundle authors may replace a single capability by providing
a different binding (e.g. ``ctx.provide("decision_gate", MyGate())``);
they do not subclass :class:`SubgraphRuntime`.

The module does not carry an :func:`@plugin` decorator — the runner
plugin owns ``ctx.provide("subgraph_runner", SubgraphRunner(...))``
after constructing the runtime from ``ctx`` directly. ADR-0219 §6
explicitly chose this wiring path; no ``subgraph_runtime`` capability
key exists.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    FactoryResolutionError,
)
from lca.harness.plugin.context import UndeclaredInteractionError
from lca.harness.plugin_api import PluginContext


@runtime_checkable
class SubgraphRuntime(Protocol):
    """Capability resolution seam used by the subgraph framework layer.

    The Protocol deliberately matches the existing
    :class:`lca.harness.graph.execute.v2.node_context_factory._ScopeLike`
    shape so :class:`NodeGraphDriver` accepts both interchangeably.
    """

    def resolve(self, capability: str) -> Any:
        """Return the capability instance bound to ``capability``.

        Return ``None`` for unbound capabilities. Node plugins are
        responsible for treating missing capabilities as soft failures.
        """

    def resolve_factory(self, factory: str, region: str) -> Any:
        """Composite-key lookup with no fallback.

        Looks up exactly ``f"{region}::{factory}"``; ``region`` must be
        non-empty. Raises :class:`FactoryResolutionError` when the
        composite key has no binding.
        """
        ...


class PluginContextBackedRuntime:
    """Default :class:`SubgraphRuntime` that resolves from a ``PluginContext``.

    ``resolve(capability)`` delegates to ``ctx.require(capability)``.
    ``KeyError`` and ``UndeclaredInteractionError`` are coerced to
    ``None`` so the :class:`NodeRuntimeView` soft-fail semantics are
    preserved; node plugins that declared ``requires=(...)`` are
    already validated at boot by the PluginContext layer, so the
    soft-fail here only kicks in for capabilities the current
    profile intentionally omitted (e.g. ``supports_shortcut`` when
    no shortcut path exists).
    """

    def __init__(self, *, ctx: PluginContext) -> None:
        self._ctx = ctx

    def resolve(self, capability: str) -> Any:
        try:
            return self._ctx.require(capability)
        except (KeyError, UndeclaredInteractionError):
            return None

    def resolve_factory(self, factory: str, region: str) -> Any:
        """Resolve a ``(factory, region)`` pair via composite key.

        Looks up exactly ``f"{region}::{factory}"``. Raises
        :class:`FactoryResolutionError` when the composite key has no
        binding. ``region`` must be non-empty; callers fall back from
        ``BundleGraphNode.region`` to ``BundleGraphSpec.region`` before
        invoking this method (see :class:`NodeGraphDriver`).
        """
        if not region:
            raise FactoryResolutionError(factory, region)
        val = self.resolve(f"{region}::{factory}")
        if val is not None:
            return val
        raise FactoryResolutionError(factory, region)


__all__ = ["PluginContextBackedRuntime", "SubgraphRuntime"]
