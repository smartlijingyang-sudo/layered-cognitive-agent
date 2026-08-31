"""Normalized receipts for effects executed in the world plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EffectOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EffectReceipt:
    """Serializable tool/effect result used by reflection and recovery."""

    invocation_id: str
    outcome: EffectOutcome
    idempotency_key: str
    provider: str
    output_ref: str | None = None
    error_code: str | None = None
    retryable: bool = False
    compensation_available: bool = False

    def __post_init__(self) -> None:
        if not self.invocation_id.strip() or not self.provider.strip():
            raise ValueError("invocation_id and provider must not be empty")
        if not self.idempotency_key.strip():
            raise ValueError("effect receipt requires an idempotency key")
        if self.outcome is EffectOutcome.SUCCEEDED and self.error_code:
            raise ValueError("succeeded effect cannot carry an error code")
        if self.outcome is EffectOutcome.FAILED and not self.error_code:
            raise ValueError("failed effect must carry an error code")
        if self.retryable and self.outcome is not EffectOutcome.FAILED:
            raise ValueError("only failed effects can be retryable")


def receipt_from_dispatcher(
    value: object,
    *,
    invocation_id: str,
    provider: str,
) -> EffectReceipt:
    """Normalize the legacy gateway mapping into an explicit receipt."""

    if not isinstance(value, dict):
        raise ValueError("gateway effect output must be a mapping")
    key = value.get("idempotency_key")
    if not isinstance(key, str) or not key:
        raise ValueError("gateway receipt must contain idempotency_key")
    error_code = value.get("error_code")
    return EffectReceipt(
        invocation_id=invocation_id,
        outcome=EffectOutcome.FAILED if error_code else EffectOutcome.SUCCEEDED,
        idempotency_key=key,
        provider=provider,
        output_ref=value.get("output_ref") if isinstance(value.get("output_ref"), str) else None,
        error_code=error_code if isinstance(error_code, str) else None,
        retryable=bool(value.get("retryable", False)),
    )


__all__ = ["EffectOutcome", "EffectReceipt", "receipt_from_dispatcher"]
