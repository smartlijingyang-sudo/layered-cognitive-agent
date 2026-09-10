"""Typed port registry (ADR-0219 §5) — closed-set cross-node data flow.

Per ADR-0219 §5: ``PortRegistry`` is the typed replacement for the legacy
``PortContext`` (ADR-0218 §3.5). Port names are the closed ``PortName``
Literal from ``lca.contracts.protocols.declarative.declarative_1.ports``;
mypy / pyright reject unknown names at compile time.

Responsibility scope:
- store and retrieve port values typed by the ``PortName`` Literal;
- project the active set of declared ports into a ``NodeInput``;
- merge an inner graph's exit ports onto the outer node's ``outputs``.

Out of scope:
- know about ``NodeExecutor`` / ``PhaseResult``;
- call ``factory`` / ``scope``;
- mutate outer ``AgentState`` directly.

D5 consumer: ``NodeGraphDriver.run()`` main loop (per node: build_input
before; merge_output after; exit_subgraph when the inner graph terminates).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName


class PortRegistry:
    """Typed cross-node port shared context.

    - ``set_outer_input(ports)``: outer drive passes initial input (if any).
    - ``merge_output(port_values)``: post-node merge (setdefault: outer input wins).
    - ``build_input(declared_ports)``: pre-node, project declared ports into a NodeInput.
    - ``exit_subgraph(outer_outputs)``: project the inner-graph terminal ports
      onto the outer node's ``outputs`` field (per ADR-0217 §3.3.3).

    Missing-port policy: no error on missing keys; the receiving plugin
    handles the empty value. This matches ADR-0218 §3.5 iron rule 2.
    """

    __slots__ = ("_ports",)

    def __init__(self) -> None:
        self._ports: dict[PortName, Any] = {}

    def set_outer_input(self, ports: Mapping[PortName, Any]) -> None:
        """Outer drive input: keys enter the registry verbatim."""
        self._ports.update(dict(ports))

    def merge_output(self, port_values: Mapping[PortName, Any]) -> None:
        """Merge a node's output into the registry (outer input wins)."""
        for k, v in port_values.items():
            self._ports.setdefault(k, v)

    def build_input(self, declared_ports: tuple[PortName, ...]) -> NodeInput:
        """Project the active port set into a typed NodeInput."""
        port_values: dict[PortName, Any] = {p: self._ports.get(p) for p in declared_ports}
        return NodeInput(port_values=port_values)

    def exit_subgraph(
        self, outer_outputs: tuple[PortName, ...]
    ) -> dict[PortName, Any]:
        """Project inner-graph terminal ports onto the outer node's outputs.

        Per ADR-0217 §3.3.3 (port passthrough — iron rule 1):
        ``inner_graph`` 终止端口名 ∈ outer 节点 ``outputs`` 字段 → 透传
        到 outer PortContext. 缺 port 不报错, outer 节点 ``build_input``
        走缺省填空的策略(铁律 2)。

        Iron rule 4: this PortRegistry is the *inner* graph's local one;
        after returning, the caller drops it.  Only the dict survives.
        """
        outer_input: dict[PortName, Any] = {}
        for port in outer_outputs:
            if port in self._ports:
                outer_input[port] = self._ports[port]
        return outer_input


__all__ = ["PortRegistry"]