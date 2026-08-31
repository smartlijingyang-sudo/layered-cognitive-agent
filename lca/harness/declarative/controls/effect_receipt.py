"""Normalize effect gateway outputs at the declarative harness seam.

An effect handler may legitimately return any domain value, including a mapping
that happens to contain a ``result`` key.  Only the complete, versioned shape
written by ``RegistryEffectDispatcher`` is an idempotency receipt.  This adapter
keeps that distinction explicit before a phase publishes its next artifact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_phase_graph import DeclarativeValidationError

_RECEIPT_FIELDS = frozenset({"receipt", "result", "plan_ref", "idempotency_key", "operation"})


@dataclass(frozen=True, slots=True)
class EffectReceiptView:
    """The domain output and auditable record produced by one effect gateway call."""

    output: object
    audit_record: object
    is_idempotency_receipt: bool


def adapt_effect_receipt(value: object) -> EffectReceiptView:
    """Separate a verified idempotency receipt from an arbitrary effect output.

    A plain value is both the domain output consumed by the next phase and the
    audit value committed to the Journal.  A complete receipt instead exposes
    its ``result`` as the domain output while preserving the entire receipt for
    idempotency and audit replay.
    """
    if not isinstance(value, Mapping) or "receipt" not in value:
        return EffectReceiptView(
            output=value,
            audit_record=value,
            is_idempotency_receipt=False,
        )

    missing = _RECEIPT_FIELDS.difference(value)
    if missing:
        missing_fields = ", ".join(sorted(missing))
        raise DeclarativeValidationError(
            "RT-003",
            f"idempotency receipt is missing required fields: {missing_fields}",
        )
    for field in ("receipt", "plan_ref", "idempotency_key", "operation"):
        if not isinstance(value[field], str) or not value[field]:
            raise DeclarativeValidationError(
                "RT-003",
                f"idempotency receipt has invalid {field!r} field",
            )
    return EffectReceiptView(
        output=value["result"],
        audit_record=dict(value),
        is_idempotency_receipt=True,
    )


__all__ = ["EffectReceiptView", "adapt_effect_receipt"]
