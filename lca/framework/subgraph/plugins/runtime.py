"""SubgraphRuntime abstraction + Cordis-backed default implementation.

Per plan §3.2 / §13.3:

- :class:`SubgraphRuntime` (Protocol) is the seam between the framework
  layer and the runtime layer that owns concrete capability instances.
- The framework calls ``runtime.resolve(capability)`` to look up
  capabilities (Reasoner, DecisionGate, …); it does not import any
  provider class.
- :class:`CordisBackedRuntime` is the default implementation, sourced
  from a Cordis ``Context``. Cordis itself is not a runtime —
  :class:`SubgraphRuntime` is the framework-facing abstraction; a
  ``Mapping[str, Any]``-backed fake is equally valid for tests.

This module does not carry ``@plugin`` for the runtime class itself:
runtime is provided via ``setup`` which calls ``ctx.provide`` on the
default ``CordisBackedRuntime`` instance.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cordis import Context  # noqa: TC002

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    FactoryResolutionError,
)


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


class CordisBackedRuntime:
    """Default :class:`SubgraphRuntime` that resolves from a Cordis ``Context``.

    Resolution walks the Cordis binding chain so the nearest scope
    wins (matches :func:`collect_context_bindings` semantics).

    Cordis does not provide a per-key ``resolve`` API directly; this
    class performs the same lookup by walking ``own_bindings`` along
    the ``parent`` chain. The walk is bounded by the parent pointer
    cycle, which Cordis guarantees terminates at ``None``.
    """

    def __init__(self, *, ctx: Context) -> None:
        self._ctx = ctx

    def resolve(self, capability: str) -> Any:
        node: Any = self._ctx
        while node is not None:
            own = getattr(node, "own_bindings", None)
            if isinstance(own, dict) and capability in own:
                return own[capability]
            node = getattr(node, "parent", None)
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


__all__ = ["CordisBackedRuntime", "SubgraphRuntime"]
