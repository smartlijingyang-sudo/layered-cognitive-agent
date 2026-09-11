"""Cognitive close-out — SSOT for inner→outer subgraph port projection.

Per ADR-0219 §10.11.5: the set of fields the inner subgraph forwards
to the outer node's port input is owned by the cognition layer, not
the graph layer. ``CLOSE_OUT_FIELDS`` is the typed tuple; it is the
single point of truth for the five canonical phase-artifact fields.

Adding a new close-out field (e.g. ``intent``) requires editing this
tuple **and** amending ADR-0219 §10.11.5. ``PhaseOutput`` (in
``lca.framework.subgraph.plugins.channel`` previously derived its field set
from this tuple via ``Pydantic.create_model``.

No I/O. No third-party deps. No environment reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
)

CLOSE_OUT_FIELDS: tuple[str, ...] = (
    "decision",
    "observation",
    "receipt",
    "reflection",
    "response",
)
"""SSOT for the five canonical phase-artifact fields forwarded from
inner-subgraph close-out to the outer node's port input.

The tuple is ordered by priority: a later ``PhaseOutput`` overwrites
an earlier one for the same field. The first non-None value wins per
field per inner-subgraph run."""


_CLOSE_OUT_TYPES: Mapping[str, type] = {
    "decision": Decision,
    "observation": Observation,
    "receipt": EffectReceipt,
    "reflection": Reflection,
    "response": LLMResponse,
}
"""Field name → typed payload class. Consumed by ``PhaseOutput`` to
build its field set without re-listing the names."""


class CognitiveCloseOut:
    """Default :class:`SubgraphCloseOut` implementation.

    For each inner-subgraph ``PhaseOutput`` in ``inner_outputs``:
    scan :data:`CLOSE_OUT_FIELDS` in priority order; copy the first
    non-None value of each field into the returned mapping. Later
    inner outputs may overwrite earlier ones for the same field
    (``last-write-wins`` per field).
    """

    def project(
        self,
        inner_outputs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        projected: dict[str, Any] = {}
        for output in inner_outputs.values():
            for field_name in CLOSE_OUT_FIELDS:
                value = getattr(output, field_name, None)
                if value is not None and field_name not in projected:
                    projected[field_name] = value
        return projected


def close_out_types() -> Mapping[str, type]:
    """Return the field-name → typed-payload-class mapping.

    Used by ``PhaseOutput`` to derive its field set. Exposed as a
    function (not a module attribute) so callers can't mutate the
    shared mapping.
    """
    return _CLOSE_OUT_TYPES


__all__ = [
    "CLOSE_OUT_FIELDS",
    "CognitiveCloseOut",
    "close_out_types",
]
