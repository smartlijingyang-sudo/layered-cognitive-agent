"""PortRegistry — typed port store for one :class:`Plan` execution.

The kernel builds a :class:`PortRegistry` per visit and reuses it
across the outer loop iterations of that visit (``PlanInterpreter.run``
shares one registry between ``stop.main → perceive.main`` round
trips). Strategies receive a :class:`NodeInput` built from the
registry via :meth:`build_input`; their :class:`NodeOutput` is merged
back via :meth:`merge_output`.

Two merge semantics (ADR-0217 §3.3.3):

- :meth:`set_outer_input` — outer caller (kernel / outer plan) seeds
  the registry; existing values are kept (iron rule 1: outer input
  wins on first seed, never overwrites a value the inner plan wrote).
- :meth:`merge_output` — inner-node outputs overwrite existing values
  (iron rule 5: last-write-wins across iterations, so stop-policy
  typed-port inputs are always fresh for the current iteration).

The registry knows port names; it never knows business DTO names.
The :class:`lca.cognition.wire.close_out_adapter.CloseOutAdapter` is
the bridge that names a business DTO for each port.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

from lca.contracts.protocols.graph.errors import UnsetPortError
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

    _ports: dict[PortName, Any] = PrivateAttr(default_factory=dict)
    _port_types: dict[PortName, type] = PrivateAttr(default_factory=dict)

    def set_outer_input(self, ports: Mapping[PortName, Any]) -> None:
        """Seed the registry from an outer caller (kernel / outer plan).

        ADR-0217 §3.3.3 iron rule 1: outer input wins on first seed;
        existing values are kept (setdefault).
        """
        for name, value in ports.items():
            self._ports.setdefault(name, value)

    def merge_output(
        self,
        port_values: Mapping[PortName, Any],
        *,
        payload_types: Mapping[PortName, type] | None = None,
    ) -> None:
        """Merge one node's outputs into the registry.

        ADR-0217 §3.3.3 iron rule 5: last-write-wins across iterations.
        Outer callers re-enter the same registry across outer-loop
        iterations (e.g. ``stop.main → perceive.main``); without this
        rule, a stale typed port from step 1 would shadow fresh outputs
        from step 2 onwards, breaking stop-policy convergence.

        D4: ``payload_types`` may be supplied explicitly (typically by
        the interpreter, which reads the node's
        ``NodeIOSchema.outputs``). For each port whose value is a
        :class:`pydantic.BaseModel` subclass instance, the payload
        type is auto-registered so :class:`PortReader` can navigate
        into typed fields (``Predicate.field`` access) even when the
        caller did not supply ``payload_types``. Values that are not
        BaseModels and have no explicit type are stored as dynamic.
        """
        types = payload_types or {}
        for name, value in port_values.items():
            self._ports[name] = value
            payload_type = types.get(name)
            if payload_type is None and isinstance(value, type):
                # isinstance check below — keep isinstance() branches
                # below readable; skip when ``value`` itself is a class.
                continue
            if payload_type is None and isinstance(value, BaseModel):
                payload_type = type(value)
            if payload_type is not None and isinstance(payload_type, type):
                self._port_types[name] = payload_type

    def build_input(
        self, declared_ports: tuple[PortName, ...], *, consumer_node: str = ""
    ) -> NodeInput:
        """Project the active port set into a typed :class:`NodeInput`.

        Missing ports yield ``None`` (no error) — the receiving node
        handles empty values via :meth:`NodeInput.require` if it cares.
        """
        port_values: dict[PortName, Any] = {name: self._ports.get(name) for name in declared_ports}
        return NodeInput(port_values=port_values, consumer_node=consumer_node)

    def exit_subgraph(self, outer_outputs: tuple[PortName, ...]) -> dict[PortName, Any]:
        """Project the inner-graph terminal ports onto outer outputs.

        Iron rule 1 (ADR-0217 §3.3.3): ports named in ``outer_outputs``
        are forwarded from this registry into the outer caller.
        Missing ports yield nothing (no error — iron rule 2).
        """
        return {name: self._ports[name] for name in outer_outputs if name in self._ports}

    def snapshot(self) -> Mapping[PortName, Any]:
        """Read-only view of the current port store."""
        return dict(self._ports)

    def has_port(self, name: PortName) -> bool:
        """Return True iff ``name`` is set in the port store.

        Used by the close-out adapter (D10) to skip inner ports that
        were never written without raising on :meth:`read`.
        """
        return name in self._ports

    # --- typed read / write (Task 3 / D3) ---

    def read(self, name: PortName) -> Any:
        """Read a port value; raise :class:`UnsetPortError` if not set.

        Unlike :meth:`build_input` (which yields ``None`` for missing
        ports), ``read`` fails loud — callers that need the port must
        get it or hear about it immediately.
        """
        if name not in self._ports:
            raise UnsetPortError(
                f"port {name!r} has not been written to the registry",
                port_name=name,
            )
        return self._ports[name]

    def port_type(self, name: PortName) -> type | None:
        """Return the payload_type registered for ``name``, or ``None``.

        Ports set via :meth:`merge_output` / :meth:`set_outer_input`
        have no type info (``None``). Use :meth:`set_typed_port` to
        register a type alongside the value.
        """
        return self._port_types.get(name)

    def set_typed_port(
        self,
        name: PortName,
        value: Any,
        *,
        payload_type: type | None = None,
    ) -> None:
        """Store a port value and optionally register its payload_type.

        Follows last-write-wins semantics (same as :meth:`merge_output`).
        When ``payload_type`` is ``None``, only the value is stored —
        :meth:`port_type` will return ``None`` for this port.
        """
        self._ports[name] = value
        if payload_type is not None:
            self._port_types[name] = payload_type
        else:
            self._port_types.pop(name, None)


__all__ = ["PortRegistry"]
