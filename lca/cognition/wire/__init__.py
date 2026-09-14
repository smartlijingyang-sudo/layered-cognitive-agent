"""Cognition wire layer — Anti-Corruption Layer between framework and cognition.

The framework graph kernel (in :mod:`lca.framework.graph`) must never
know business DTO names like ``Decision`` / ``Observation`` /
``Reflection`` / ``EffectReceipt``. The cognition layer owns those
names. This subpackage owns the **typed bridge** between the two:
the :class:`CloseOutAdapter` that translates inner subgraph port
names to outer port names by generic name match (with an explicit
rename map when the inner and outer vocabularies differ), and the
:class:`AgentClientAdapter` that lets the framework call cognition's
team machinery without knowing DTO names.

What lives here (post-typed-port-graph-redesign):

- :mod:`close_out_adapter` — :class:`CloseOutAdapter`, the single
  seam that translates inner-subgraph ports onto the outer node's
  output ports.
- :mod:`agent_client_adapter` — :class:`AgentClientAdapter`, the
  single seam the framework uses to talk to agents.
- :mod:`envelope` — pre-existing transport envelope helper (untouched).
- :mod:`registry_factory` — pre-existing transport registry helper.

What does NOT live here:

- Business DTOs (live in :mod:`lca.contracts.models.core.execution`).
- Framework port schema (lives in :mod:`lca.contracts.protocols.graph`).
- Any actual graph execution logic.

Layer rule (enforced by ``scripts/check_framework_cognition_boundary.py``):

- The framework imports from this subpackage; this subpackage may
  not import from the framework. The adapter is framework-facing
  and operates on a duck-typed port store (``has_port`` + ``read``);
  the framework's :class:`lca.framework.graph.port_registry.PortRegistry`
  satisfies the interface.
"""

from lca.cognition.wire.agent_client_adapter import AgentClientAdapter
from lca.cognition.wire.close_out_adapter import CloseOutAdapter

__all__ = [
    "AgentClientAdapter",
    "CloseOutAdapter",
]
