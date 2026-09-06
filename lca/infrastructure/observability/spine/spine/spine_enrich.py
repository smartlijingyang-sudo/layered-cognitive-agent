"""Spine payload enrichment — FieldProducer merge + I17 (FactGateway seam).

Enrichment runs at :meth:`lca.loop.fact_gateway.DefaultFactGateway.publish_ep`
and at the Session append hook when a run-bound ``SessionAppendHook`` is
installed. ``EmitPipeline.emit`` delegates here only on hook-less test paths.

# COMPAT(owner: ADR-0194 P2-06, from: lca.infrastructure.observability.spine.spine_enrich,
#         to: infrastructure/observability/spine/spine_enrich (FactGateway SSOT),
#         delete_when: rg 'lca.infrastructure.observability.spine.spine.spine_enrich' lca/ = 0
#                       (re-export shim only),
#         forbidden_new_usage: duplicate FieldProducer merge outside this module)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer
from lca.infrastructure.observability.spine.event.event_record import Channel
from lca.infrastructure.observability.spine.manifest.manifest import EXECUTION_POINTS

log = logging.getLogger(__name__)

__all__ = [
    "EnrichResult",
    "I17Violation",
    "enrich_spine_payload",
    "get_active_field_producers",
    "get_active_spine_enricher",
    "reset_active_field_producers",
    "reset_active_spine_enricher",
    "set_active_field_producers",
    "set_active_spine_enricher",
]


class I17Violation(Exception):  # noqa: N818 — name mandated by Task 9.2 brief
    """Raised when a ``*.start`` event is emitted without ``source_location``."""


@dataclass(frozen=True, slots=True)
class EnrichResult:
    """Merged spine payload plus optional producer failure sidecar entries."""

    merged: dict[str, Any]
    producer_failures: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)


def _noop(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    return None


_NO_OP_FN: Any = _noop


_SpineEnricher = Callable[..., EnrichResult]

_active_field_producers: ContextVar[list[FieldProducer] | None] = ContextVar(
    "lca_active_field_producers",
    default=None,
)

_active_spine_enricher: ContextVar[_SpineEnricher | None] = ContextVar(
    "lca_active_spine_enricher",
    default=None,
)


def set_active_field_producers(
    producers: list[FieldProducer] | None,
) -> list[FieldProducer] | None:
    """Install process-local FieldProducer list; returns previous list."""
    previous = _active_field_producers.get()
    _active_field_producers.set(producers)
    return previous


def reset_active_field_producers(token: Token[list[FieldProducer] | None]) -> None:
    _active_field_producers.reset(token)


def get_active_field_producers() -> list[FieldProducer] | None:
    return _active_field_producers.get()


def set_active_spine_enricher(
    getter: _SpineEnricher | None,
) -> _SpineEnricher | None:
    """Install process-local enricher callable (hook-less test compat); returns previous."""
    previous = _active_spine_enricher.get()
    _active_spine_enricher.set(getter)
    return previous


def reset_active_spine_enricher(token: Token[_SpineEnricher | None]) -> None:
    _active_spine_enricher.reset(token)


def get_active_spine_enricher() -> _SpineEnricher | None:
    return _active_spine_enricher.get()


def enrich_spine_payload(
    *,
    producers: list[FieldProducer],
    execution_point: str,
    channel: Channel,
    caller_payload: dict[str, Any] | None,
    span_ctx: Any | None,
) -> EnrichResult:
    """Merge FieldProducer pre-fields, apply caller payload (D11), enforce I17."""
    del channel  # reserved for future channel-sensitive producers
    merged: dict[str, Any] = {}
    producer_failures: list[tuple[Any, dict[str, Any]]] = []

    for producer in sorted(producers, key=lambda p: p.priority):
        if not producer.enabled:
            continue
        try:
            fields = producer.produce(
                fn=_NO_OP_FN,
                args=(),
                kwargs={},
                ctx=None,
                span=span_ctx,
                phase="pre",
            )
        except Exception as exc:
            log.warning(
                "spine_enrich: producer=%s raised %s; skipping",
                getattr(producer, "name", repr(producer)),
                exc,
                exc_info=True,
            )
            continue
        if not fields:
            continue
        sidecar = fields.pop("_lca_failures", None)
        if isinstance(sidecar, list):
            for entry in sidecar:
                if isinstance(entry, dict):
                    producer_failures.append((producer, entry))
        merged.update(fields)

    if caller_payload:
        merged.update(caller_payload)

    if execution_point not in EXECUTION_POINTS:
        raise ValueError(
            f"UnknownExecutionPoint({execution_point!r}): not in EXECUTION_POINTS whitelist"
        )

    if execution_point.endswith(".start") and "source_location" not in merged:
        raise I17Violation(
            f"I17: execution_point={execution_point!r} requires "
            f"'source_location' in payload (ADR-0165.1 §96; "
            f"ADR-i17-tb spine-wide strong contract)"
        )

    return EnrichResult(merged=merged, producer_failures=producer_failures)
