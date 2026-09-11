"""Port name closure for graph node IO.

Re-exports the typed :data:`PortName` Literal from the existing
``lca.contracts.atoms.ports`` location so the graph protocol package
has a single canonical import surface. New code should depend on
``lca.contracts.protocols.graph.ports.PortName``.

Existing imports of :data:`lca.contracts.atoms.ports.PortName` continue
to resolve; this module is a thin alias, not a relocation.
"""
from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.ports import PortName

__all__ = ["PortName"]