"""Typed port-name brand for graph node IO.

Re-exports :data:`PortName` from the declarative layer so the graph
protocol package has a single canonical import surface. New code should
depend on ``lca.contracts.protocols.graph.ports.PortName``.
"""
from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.ports import PortName

__all__ = ["PortName"]
