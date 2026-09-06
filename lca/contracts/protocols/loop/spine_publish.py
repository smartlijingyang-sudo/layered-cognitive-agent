"""Spine publish seam — loop mechanism reads, infrastructure registers (ADR-0194)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "SpineEnrichResult",
    "SpinePayloadEnricher",
    "get_active_field_producers",
    "get_active_spine_enricher",
    "is_session_ssot_hook_active",
    "mark_session_ssot_hook_active",
    "reset_session_ssot_hook_active",
    "set_active_field_producers",
    "set_active_spine_enricher",
]


@dataclass(frozen=True, slots=True)
class SpineEnrichResult:
    """Merged spine payload for FactGateway.publish_ep."""

    merged: dict[str, Any]
    producer_failures: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)


@runtime_checkable
class SpinePayloadEnricher(Protocol):
    def __call__(
        self,
        *,
        execution_point: str,
        channel: str,
        caller_payload: dict[str, Any] | None,
        span_ctx: Any | None,
    ) -> SpineEnrichResult: ...


_session_ssot_hook_active: ContextVar[bool] = ContextVar(
    "lca_session_ssot_hook_active",
    default=False,
)

_active_field_producers: ContextVar[list[Any] | None] = ContextVar(
    "lca_active_field_producers",
    default=None,
)

_active_spine_enricher: ContextVar[SpinePayloadEnricher | None] = ContextVar(
    "lca_active_spine_enricher",
    default=None,
)


def is_session_ssot_hook_active() -> bool:
    return _session_ssot_hook_active.get()


def mark_session_ssot_hook_active(active: bool) -> Token[bool]:
    return _session_ssot_hook_active.set(active)


def reset_session_ssot_hook_active(token: Token[bool]) -> None:
    _session_ssot_hook_active.reset(token)


def set_active_field_producers(producers: list[Any] | None) -> list[Any] | None:
    previous = _active_field_producers.get()
    _active_field_producers.set(producers)
    return previous


def get_active_field_producers() -> list[Any] | None:
    return _active_field_producers.get()


def set_active_spine_enricher(
    enricher: SpinePayloadEnricher | None,
) -> SpinePayloadEnricher | None:
    previous = _active_spine_enricher.get()
    _active_spine_enricher.set(enricher)
    return previous


def get_active_spine_enricher() -> SpinePayloadEnricher | None:
    return _active_spine_enricher.get()
