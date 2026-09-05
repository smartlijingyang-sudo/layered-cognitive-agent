"""``spine.emit_pipeline`` — commit + anomaly seam (enrich → Session hook).

FieldProducer merge and I17 enforcement live in
:mod:`lca.plugins.observability.spine.spine_enrich` and run at the
Session append hook when a run is bound (ADR-0186 wave 2).

Anomaly detection runs on committed Session spine events via
``lca.plugins.session.spine_anomaly`` when a Session hook is active;
``EmitPipeline.emit`` invokes anomaly only on the hook-less fallback path.

# COMPAT(owner: ADR-0186 wave-2, from: EmitPipeline owns FieldProducer merge,
#         to: spine_enrich + SessionAppendHook,
#         delete_when: rg 'enrich_spine_payload' lca/plugins/observability/spine/emit_pipeline.py = 1
#                       (import-only re-export path) AND hook-less enrich branch deleted,
#         forbidden_new_usage: new FieldProducer.produce calls outside spine_enrich)
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast, runtime_checkable

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.spine.producer import FieldProducer
from lca.contracts.protocols.declarative.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import (
    PluginContext,
    PluginKind,
    plugin,
)
from lca.infrastructure.observability.loop_cursor._spine_port import get_session_append_hook
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.plugins.observability.spine.spine_enrich import (
    I17Violation,
    enrich_spine_payload,
    set_active_spine_enricher,
)

log = logging.getLogger(__name__)


# ── contracts ────────────────────────────────────────────────────────


@runtime_checkable
class _AnomalyLike(Protocol):
    def on_event(self, event: EventRecord) -> None: ...


class EmitPipeline:
    """Commit spine events and run anomaly detection on sealed records."""

    def __init__(
        self,
        producers: list[FieldProducer],
        anomaly: _AnomalyLike,
    ) -> None:
        self._producers: list[FieldProducer] = sorted(
            producers, key=lambda producer: producer.priority
        )
        self._anomaly: _AnomalyLike = anomaly

    @property
    def producers(self) -> tuple[FieldProducer, ...]:
        return tuple(self._producers)

    @property
    def anomaly(self) -> _AnomalyLike:
        return self._anomaly

    def _resolve_payload(
        self,
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None,
        span_ctx: Any | None,
    ) -> tuple[dict[str, Any], list[tuple[Any, dict[str, Any]]]]:
        if get_session_append_hook() is not None:
            return dict(caller_payload or {}), []
        result = enrich_spine_payload(
            producers=list(self._producers),
            execution_point=execution_point,
            channel=channel,
            caller_payload=caller_payload,
            span_ctx=span_ctx,
        )
        return result.merged, result.producer_failures

    def emit(
        self,
        *,
        execution_point: str,
        channel: Channel,
        span_ctx: Any,
        caller_payload: dict[str, Any] | None,
        spine: EventSpine,
        outcome: Outcome | None = None,
        phase: Phase = "live",
        reason: str | None = None,
    ) -> EventRecord:
        merged, producer_failures = self._resolve_payload(
            execution_point=execution_point,
            channel=channel,
            caller_payload=caller_payload,
            span_ctx=span_ctx,
        )

        record = spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=merged,
            outcome=outcome,
            span_ctx=span_ctx,
            phase=phase,
            reason=reason,
        )

        if producer_failures:
            for producer_origin, entry in producer_failures:
                try:
                    spine.append(
                        execution_point="spine.producer.failure",
                        channel="error",
                        caller_payload={
                            "producer": getattr(producer_origin, "name", "unknown"),
                            "key": entry.get("key"),
                            "exception_class": entry.get("exception_class"),
                            "traceback_text": entry.get("traceback_text"),
                            "span_id": getattr(span_ctx, "span_id", None),
                            "outer_execution_point": execution_point,
                        },
                        outcome="failure",
                        span_ctx=span_ctx,
                        phase=phase,
                    )
                except Exception as exc:
                    log.warning(
                        "emit_pipeline: spine.producer.failure "
                        "publication failed err=%s; record still emitted",
                        exc,
                        exc_info=True,
                    )

        if get_session_append_hook() is None:
            try:
                self._anomaly.on_event(record)
            except Exception as exc:
                log.warning(
                    "emit_pipeline: anomaly=%s raised %s; record still emitted",
                    getattr(self._anomaly, "name", type(self._anomaly).__name__),
                    exc,
                    exc_info=True,
                )

        return record


def _looks_like_field_producer(value: object) -> bool:
    return (
        hasattr(value, "produce")
        and hasattr(value, "priority")
        and hasattr(value, "enabled")
        and callable(getattr(value, "produce", None))
    )


@plugin(
    id="spine.emit_pipeline",
    provides=("emit_pipeline",),
    requires=("field_producer.*", "deriver.anomaly"),
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "Emit pipeline — FieldProducer enrich at Session hook; commit via "
        "EventSpine.append and invoke bound anomaly detector (I15)."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_emit_pipeline",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_source",)),
        observability=EvidenceContract(
            descriptors=("spine.emit_pipeline",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("field_producer.*", "deriver.anomaly"),
        emits=("emit_pipeline",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config

    matched = ctx.require_matching("field_producer.")
    producers: list[FieldProducer] = [
        cast("FieldProducer", value)
        for value in matched.values()
        if _looks_like_field_producer(value)
    ]
    anomaly = ctx.require("deriver.anomaly")
    pipeline = EmitPipeline(producers=producers, anomaly=anomaly)
    ctx.provide("emit_pipeline", pipeline)

    from lca.harness.declarative.compile.instrument_wrap import (
        set_active_pipeline_accessor,
    )

    set_active_pipeline_accessor(lambda: pipeline)

    def _enricher(
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None,
        span_ctx: Any | None,
    ) -> Any:
        return enrich_spine_payload(
            producers=list(pipeline.producers),
            execution_point=execution_point,
            channel=channel,
            caller_payload=caller_payload,
            span_ctx=span_ctx,
        )

    set_active_spine_enricher(_enricher)

    log.debug(
        "spine.emit_pipeline: setup complete producers=%d anomaly=%s",
        len(producers),
        getattr(anomaly, "name", type(anomaly).__name__),
    )


__all__ = ["EmitPipeline", "I17Violation", "setup"]
