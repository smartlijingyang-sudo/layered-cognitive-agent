"""Subgraph framework Protocols — capability resolution seam.

Defines the abstraction boundary between the subgraph framework layer and
the Runtime layer that owns concrete capability instances.

Per plan §13.3 / §3.2:
- The subgraph framework calls ``runtime.resolve(capability_key)`` to fetch
  instances; it does not import concrete capability providers.
- The Runtime layer owns the actual resolution implementation
  (``CordisBackedRuntime`` in :mod:`lca.framework.subgraph.plugins.runtime`).
- The framework does not know about capability names either — those flow
  through ``NodeRuntimeView`` fields declared by node plugins.

Protocol definition does not carry ``@plugin`` (per plan §13.2 / R4):
protocols are not plugins.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SubgraphRuntime(Protocol):
    """Capability resolution abstraction for subgraph framework plugins.

    Implementations are responsible for sourcing capability instances
    from their backing scope (cordis container, mapping, fake, etc.).
    Subgraph framework code calls ``resolve(key)`` and does not import
    the concrete runtime class.
    """

    def resolve(self, capability: str) -> Any:
        """Return the capability instance for ``capability``.

        Return ``None`` when the capability is not bound. Node plugin
        code is responsible for handling the missing-capability case
        (e.g., by returning a no-op ``NodeOutput``).
        """
        ...


__all__ = ["SubgraphRuntime"]
