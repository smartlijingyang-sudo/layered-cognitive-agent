"""PortRegistry — typed port store for one :class:`Plan` visit.

The kernel builds a :class:`PortRegistry` per visit (or shares one
across visits of the same plan). Strategies receive a :class:`NodeInput`
built from the registry via :meth:`build_input`; their :class:`NodeOutput`
is merged back via :meth:`merge_output`. The registry never mutates
its own typed view of a port once a node has consumed it (setdefault
semantics — outer input wins, see ADR-0217 §3.3.3 iron rule 1).

The registry knows port names; it never knows business DTO names.
The :class:`lca.cognition.wire.close_out_adapter.CloseOutAdapter` is
the bridge that names a business DTO for each port.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.node_io import NodeInput
from lca.contracts.protocols.graph.ports import PortName


class PortRegistry(BaseModel):
    """Typed port store for one :class:`Plan` execution.

    ``model_config`` allows arbitrary value types because ports carry
    business DTOs that are outside this module's contract surface.
    The contract is enforced at the seam (``NodeIOSchema`` +
    ``NodeInput.require``), not at the registry.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _ports: dict[PortName, Any] = {}

    def set_outer_input(self, ports: Mapping[PortName, Any]) -> None:
        """Seed the registry from an outer caller (kernel / outer plan)."""
        for name, value in ports.items():
            self._ports.setdefault(name, value)

    def merge_output(self, port_values: Mapping[PortName, Any]) -> None:
        """Merge one node's outputs into the registry (outer input wins)."""
        for name, value in port_values.items():
            self._ports.setdefault(name, value)

    def build_input(
        self, declared_ports: tuple[PortName, ...], *, consumer_node: str = ""
    ) -> NodeInput:
        """Project the active port set into a typed :class:`NodeInput`.

        Missing ports yield ``None`` (no error) — the receiving node
        handles empty values via :meth:`NodeInput.require` if it cares.
        """
        port_values: dict[PortName, Any] = {
            name: self._ports.get(name) for name in declared_ports
        }
        return NodeInput(port_values=port_values, consumer_node=consumer_node)

    def exit_subgraph(
        self, outer_outputs: tuple[PortName, ...]
    ) -> dict[PortName, Any]:
        """Project the inner-graph terminal ports onto outer outputs.

        Iron rule 1 (ADR-0217 §3.3.3): ports named in ``outer_outputs``
        are forwarded from this registry into the outer caller.
        Missing ports yield nothing (no error — iron rule 2).
        """
        return {name: self._ports[name] for name in outer_outputs if name in self._ports}

    def snapshot(self) -> Mapping[PortName, Any]:
        """Read-only view of the current port store."""
        return dict(self._ports)


__all__ = ["PortRegistry"]