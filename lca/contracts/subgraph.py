"""Subgraph contracts — public protocols for cross-boundary close-out.

Per ADR-0219 §10.11.5: inner→outer subgraph close-out must not embed
business field names (``decision`` / ``observation`` / ``reflection``
/ ``response``) inside the graph driver or its helpers. Field names
are the SSOT of the cognition layer; the graph layer exposes only a
typed projection seam.

This module is intentionally field-name free: ``SubgraphCloseOut`` is
a Protocol whose signature declares only a typed ``project`` method.
The implementation side (``lca.cognition.close_out.CognitiveCloseOut``)
owns the field name tuple.

No I/O. No third-party deps. No environment reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SubgraphCloseOut(Protocol):
    """Project inner-subgraph outputs onto the outer node's port input.

    Implementations decide which fields are surfaced and in which
    priority order. The graph driver holds no opinion on either; it
    only calls ``project`` and forwards the returned mapping to
    :meth:`lca.harness.graph.execute.v2._port_context.PortRegistry.set_outer_input`.

    The contract is field-name-free by design. Implementations that
    name specific keys live in the cognition layer, not here.
    """

    def project(
        self,
        inner_outputs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return the port input the outer node should consume next.

        Implementations must be pure and deterministic: same
        ``inner_outputs`` → same projection. The graph driver calls
        this method at most once per inner-subgraph close-out.
        """
        ...


__all__ = ["SubgraphCloseOut"]
