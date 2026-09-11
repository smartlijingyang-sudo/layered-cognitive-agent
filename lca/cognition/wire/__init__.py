"""Cognition wire layer — Anti-Corruption Layer between framework and cognition.

The framework graph kernel (in :mod:`lca.framework.graph`, future PRs)
must never know business DTO names like ``Decision`` /
``Observation`` / ``Reflection`` / ``EffectReceipt``. The cognition
layer owns those names. This subpackage owns the **typed bridge**
between the two: a registry of close-out fields with explicit
priority, an adapter that projects typed port values through the
bridge, and the :class:`AgentClientAdapter` that lets the framework
call cognition's team machinery without knowing DTO names.

What lives here (PR-2 + PR-6):

- :mod:`close_out_registry` — :class:`CloseOutField`, :data:`CLOSE_OUT_REGISTRY`,
  :func:`close_out_projection`.
- :mod:`close_out_adapter` — :class:`CloseOutAdapter`, the single seam
  the framework talks to for port projection.
- :mod:`agent_client_adapter` — :class:`AgentClientAdapter`, the
  single seam the framework uses to talk to agents.
- :mod:`envelope` — pre-existing transport envelope helper (untouched).
- :mod:`registry_factory` — pre-existing transport registry helper.

What does NOT live here:

- Business DTOs (live in :mod:`lca.contracts.models.core.execution`).
- Framework port schema (lives in :mod:`lca.contracts.protocols.graph`).
- Any actual graph execution logic.

Layer rule (enforced by ``scripts/check_framework_cognition_boundary.py``
in planned PR-8):

- The framework imports from this subpackage; this subpackage may
  not import from the framework.
"""
from lca.cognition.wire.agent_client_adapter import AgentClientAdapter
from lca.cognition.wire.close_out_adapter import CloseOutAdapter
from lca.cognition.wire.close_out_registry import (
    CLOSE_OUT_REGISTRY,
    CloseOutField,
    close_out_projection,
)

__all__ = [
    "AgentClientAdapter",
    "CLOSE_OUT_REGISTRY",
    "CloseOutAdapter",
    "CloseOutField",
    "close_out_projection",
]