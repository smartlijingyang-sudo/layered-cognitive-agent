"""CloseOutAdapter — generic subgraph → outer port translation.

The framework graph kernel calls :meth:`CloseOutAdapter.close_out`
when a subgraph node finishes. For each port declared in the outer
node's ``io_schema.outputs``, the adapter copies the value of the
matching inner port by name. A caller-supplied ``rename_map`` lets a
subgraph node expose one port under a different outer name when the
inner and outer DTOs use different vocabularies.

The adapter is the framework-facing ACL: framework imports from
``lca.cognition.wire``, the adapter does not import framework.
The inner registry is typed loosely (``Any``) — the adapter only
requires ``has_port`` and ``read`` methods, which
:class:`lca.framework.graph.port_registry.PortRegistry` satisfies.

Why this class instead of free functions:

- Future graph kernel can inject this adapter at boot so test
  fixtures swap projection policy without rewriting the kernel.
- A rename map is the only place where inner→outer vocabulary
  differences live; everything else is identical-name forwarding.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.node_io import PortSpec
from lca.contracts.protocols.graph.ports import PortName


@dataclass(frozen=True, slots=True)
class CloseOutAdapter:
    """Generic subgraph → outer port translator.

    ``rename_map`` maps an outer port name to its inner counterpart
    when the inner and outer vocaularies differ (e.g. an inner
    ``observation`` port surfaced as outer ``act_outcome``). Names
    not in the map are forwarded unchanged.

    Default behavior (no rename map) requires outer and inner port
    names to match; missing inner ports yield no entry (no error).
    """

    rename_map: Mapping[PortName, PortName] = field(default_factory=dict)

    def close_out(
        self,
        *,
        inner_registry: Any,
        outer_outputs: tuple[PortSpec, ...],
    ) -> dict[PortName, Any]:
        """Project inner registry ports onto the outer node's outputs.

        For each :class:`PortSpec` in ``outer_outputs``, look up the
        inner port (via ``rename_map`` if present, else by the spec
        name) and copy its value. Inner ports that are unset yield
        no entry — they are silently dropped, matching the iron
        rule 2 in :meth:`PortRegistry.exit_subgraph`.

        ``inner_registry`` only needs ``has_port(name) -> bool`` and
        ``read(name) -> Any``. Callers that raise on missing ports
        in ``read`` should first check ``has_port``; the adapter
        uses ``has_port`` before every ``read`` and skips missing
        ports without raising.
        """
        projected: dict[PortName, Any] = {}
        for spec in outer_outputs:
            inner_name = self.rename_map.get(spec.name, spec.name)
            if inner_registry.has_port(inner_name):
                projected[spec.name] = inner_registry.read(inner_name)
        return projected


__all__ = ["CloseOutAdapter"]
