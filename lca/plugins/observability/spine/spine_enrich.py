"""Spine payload enrichment — FieldProducer merge + I17 (Session SSOT seam).

Enrichment runs at the Session append boundary when a run-bound
``SessionAppendHook`` is installed; ``EmitPipeline.emit`` delegates
here only when no hook is active (unit tests / pre-boot).

# COMPAT(owner: ADR-0186 wave-2, from: enrich inside EmitPipeline.emit only,
#         to: enrich in spine_hook + shared spine_enrich module,
#         delete_when: rg 'get_session_append_hook\\(\\) is None' lca/plugins/observability/spine/emit_pipeline.py = 0
#                       AND test_wrap_uses_emit_pipeline fallback path removed,
#         forbidden_new_usage: duplicate FieldProducer merge outside spine_enrich)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer
from lca.infrastructure.observability.spine.event_record import Channel
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

log = logging.getLogger(__name__)

__all__ = [
    "EnrichResult",
    "I17Violation",
    "enrich_spine_payload",
    "get_active_spine_enricher",
    "reset_active_spine_enricher",
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

_active_spine_enricher: ContextVar[_SpineEnricher | None] = ContextVar(
    "lca_active_spine_enricher",
    default=None,
)


def set_active_spine_enricher(
    getter: _SpineEnricher | None,
) -> _SpineEnricher | None:
    """Install process-local enricher; returns previous getter."""
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
