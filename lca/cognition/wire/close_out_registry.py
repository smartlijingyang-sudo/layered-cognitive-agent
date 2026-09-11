"""Typed registry of inner→outer close-out fields.

Replaces the legacy ``CLOSE_OUT_FIELDS`` tuple + ``CognitiveCloseOut.project``
loop with a typed, priority-aware registry. The legacy symbols remain
re-exported from :mod:`lca.cognition.close_out` for backwards
compatibility; new code should depend on this module.

Why a registry and not a tuple:

- Each field carries its **priority** explicitly. The legacy code
  used tuple order with an implicit priority (decision > receipt >
  observation > reflection > response) and was a frequent source of
  "which wins?" bugs.
- Adding a field requires touching one place: this registry. The
  legacy version required updating five locations (tuple,
  ``_CLOSE_OUT_TYPES``, channel reverse-lookup, driver projection,
  interpreter fold).
- Field names are typed literals, not free strings, so a typo in a
  caller fails at mypy time, not at runtime.

Adding a field:

1. Add an entry to :data:`CLOSE_OUT_REGISTRY` with the field name,
   the payload type, and a priority (higher = wins on collision).
2. Add the matching :data:`PortName` literal entry in
   :mod:`lca.contracts.protocols.declarative.declarative_1.ports`.
3. Add a test case in ``tests/unit/cognition/wire/test_close_out_registry.py``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
)
from lca.contracts.harness.act.effect_receipt import EffectReceipt


@dataclass(frozen=True, slots=True)
class CloseOutField:
    """One typed close-out field carried between subgraph and outer plan.

    Attributes:
        name: stable identifier, must match a ``PortName`` literal
            from the graph protocol.
        payload_type: the business DTO class this field carries.
        priority: collision winner. Higher priority wins when two
            inner outputs supply the same field. Stable across the
            tuple: ordering by priority must be deterministic.
    """

    name: str
    payload_type: type
    priority: int


CLOSE_OUT_REGISTRY: tuple[CloseOutField, ...] = (
    CloseOutField(name="decision", payload_type=Decision, priority=100),
    CloseOutField(name="receipt", payload_type=EffectReceipt, priority=90),
    CloseOutField(name="observation", payload_type=Observation, priority=80),
    CloseOutField(name="reflection", payload_type=Reflection, priority=70),
    CloseOutField(name="response", payload_type=LLMResponse, priority=60),
)
"""SSOT for the five canonical phase-artifact fields forwarded from
inner-subgraph close-out to the outer node's port input.

Reorders the legacy tuple to be priority-ordered (highest first); the
priority field carries the explicit ordering that the legacy code
encoded via tuple position.

Adding a new close-out field requires appending an entry here AND
amending :data:`lca.contracts.protocols.declarative.declarative_1.ports.PortName`.
"""


def close_out_projection(
    inner_outputs: Mapping[Any, Any],
) -> dict[str, Any]:
    """Project a set of inner-subgraph outputs into an outer port mapping.

    For each entry in :data:`CLOSE_OUT_REGISTRY` (in priority order),
    scan the inner outputs and copy the first non-None value of the
    matching field. A later, lower-priority field never overwrites an
    already-set higher-priority field.

    Pure function: same input → same output. No I/O, no clock, no
    global state.
    """
    projected: dict[str, Any] = {}
    for field in sorted(CLOSE_OUT_REGISTRY, key=lambda f: -f.priority):
        for output in inner_outputs.values():
            if not hasattr(output, field.name):
                continue
            value = getattr(output, field.name, None)
            if value is not None and field.name not in projected:
                projected[field.name] = value
                break
    return projected


def field_names() -> Iterable[str]:
    """Yield close-out field names in priority order (highest first)."""
    return tuple(f.name for f in sorted(CLOSE_OUT_REGISTRY, key=lambda f: -f.priority))


__all__ = [
    "CLOSE_OUT_REGISTRY",
    "CloseOutField",
    "close_out_projection",
    "field_names",
]