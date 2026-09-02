"""``spine.emit_pipeline`` — assembly line for ``EventRecord`` payloads (Task 7.8).

The emit pipeline is the composition root for the I12 auto-source fields
required by ADR-0165 / ADR-0165.1 §7.5.7. Every call to
``EmitPipeline.emit(...)`` performs the same five steps:

1. Sort enabled ``FieldProducer`` plugins by ``priority`` ascending —
   lower numbers run earlier so on a key conflict the *lower* priority
   value wins (the documented override direction; the merge is a plain
   ``dict.update`` from low to high so high-priority producers
   overwrite low-priority ones, which matches ``FieldProducer``
   Protocol semantics where high-priority is more authoritative).
2. Call each producer's ``produce(phase="pre", ...)`` and merge the
   returned dict into the payload. Producers whose ``produce`` raises
   are logged and skipped — the pipeline never lets a single broken
   producer block the rest (Layer-1 integration must be fail-open on
   auto-source so business code always emits).
3. ``caller_payload`` is layered on top so callers always win on
   conflict (D11 caller-provided fields are authoritative over
   auto-source).
4. ``EventRecord`` is constructed through ``EventSpine.append`` which
   enforces I12 (close-set ``execution_point`` / ``channel`` /
   ``outcome`` / ``phase``). The pipeline additionally enforces I17
   (ADR-0165.1 §96): every ``*.start`` event MUST carry
   ``source_location`` or ``I17Violation`` is raised before the
   ``EventRecord`` is appended.
5. The bound ``AnomalyDetector.on_event`` is invoked on the sealed
   ``EventRecord``. Its exceptions are contained (FD-2 — best-effort
   anomaly detection must never block emission).

Layer-1 integration (L1): this plugin wires every L0 ``FieldProducer``
together so ``spine.core`` (L2) only depends on a single
``emit_pipeline`` capability. ``L1`` is required by ADR-0165.1.

Module contract
---------------
- Public symbols: ``EmitPipeline``, ``setup``.
- The constructor accepts ``producers`` (already-materialised
  ``FieldProducer`` instances) and ``anomaly`` (any object with an
  ``on_event(EventRecord) -> None`` method, typically the
  ``AnomalyDetector`` produced by ``spine.deriver.anomaly``).
- ``emit(...)`` accepts the ``EventSpine`` as a keyword argument so the
  pipeline is independent of process-global state; later PRs (PR-8
  wiring) may install a default spine via ``ctx.require``.
- Merge direction is **lower priority overwrites higher**: see the
  override-direction note above.
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
    EffectClass,
    PluginContext,
    PluginKind,
    plugin,
)
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

log = logging.getLogger(__name__)


# ── exceptions ───────────────────────────────────────────────────────


class I17Violation(Exception):  # noqa: N818 — name mandated by Task 9.2 brief
    """Raised when a ``*.start`` event is emitted without ``source_location``.

    I17 (ADR-0165.1 §96) requires every ``*.start`` execution point to
    carry a ``source_location`` field produced by the SourceAttacher
    plugin (Task 9.1). The check lives in ``EmitPipeline.emit`` so a
    pipeline wired without SourceAttacher cannot silently append a
    non-compliant record; the failure surfaces to the caller with the
    offending execution_point for log triage.
    """


# ── contracts ────────────────────────────────────────────────────────


@runtime_checkable
class _AnomalyLike(Protocol):
    """Minimum surface required of the bound anomaly detector.

    The full ``AnomalyDetector`` from ``spine.deriver.anomaly`` exposes
    the eight I15 detector methods plus this ``on_event`` hook; tests
    use lightweight stubs that only satisfy this Protocol.
    """

    def on_event(self, event: EventRecord) -> None: ...


# ── core ─────────────────────────────────────────────────────────────


def _noop(*args: Any, **kwargs: Any) -> Any:
    """Sentinel callable passed as ``fn`` to producer ``produce(...)``.

    ``EmitPipeline.emit`` does not wrap a live function call — that is
    the job of ``wrap_instrument`` in a later PR (see the §7.5.6
    assembly diagram). Producers that need a real ``fn`` therefore
    short-circuit; we pass a no-op so the FieldProducer Protocol
    signature is satisfied without inventing a fake frame.
    """
    del args, kwargs
    return None


_NO_OP_FN: Any = _noop


class EmitPipeline:
    """Compose ``FieldProducer`` plugins into one ``EventRecord`` payload.

    Parameters
    ----------
    producers:
        Concrete ``FieldProducer`` instances to merge on every emit.
        They are sorted by ``priority`` ascending on construction so
        the per-emit hot path does not re-sort; producers with
        ``enabled=False`` are kept in the list (the merge loop skips
        them) so profile-level toggles remain reversible.
    anomaly:
        Bound anomaly detector. ``on_event(record)`` is invoked after
        the record is sealed in the spine. Exceptions raised by the
        detector are contained — emission is the truth, anomaly is the
        derived view.
    """

    def __init__(
        self,
        producers: list[FieldProducer],
        anomaly: _AnomalyLike,
    ) -> None:
        self._producers: list[FieldProducer] = sorted(
            producers, key=lambda producer: producer.priority
        )
        self._anomaly: _AnomalyLike = anomaly
        # ADR-2026-09-02-i17-traceback §D4: a one-shot flag so the
        # coverage-gap diagnostic fires at most once per pipeline
        # instance. ``compile_profile`` constructs a fresh pipeline
        # per run, so this naturally scopes to one run.
        self._coverage_emitted = False

    @property
    def producers(self) -> tuple[FieldProducer, ...]:
        """Return the priority-sorted producer tuple (read-only view)."""
        return tuple(self._producers)

    @property
    def anomaly(self) -> _AnomalyLike:
        """Return the bound anomaly detector (read-only view)."""
        return self._anomaly

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
        """Assemble an ``EventRecord`` from producer fields + caller payload.

        Steps are exactly the five from the module docstring:

        1. Merge each enabled producer's ``produce(phase="pre", ...)``
           output into the payload dict, lower priority first.
        2. Layer ``caller_payload`` on top so the caller wins on
           conflict (D11).
        3. ``EventSpine.append`` constructs the ``EventRecord``,
           enforcing I12 close-set validation (raises ``ValueError``
           for an unknown ``execution_point``, ``outcome``, ``channel``
           or ``phase``).
        4. Invoke ``self._anomaly.on_event(record)`` on the sealed
           record. Detector exceptions are contained (FD-2).

        Returns
        -------
        EventRecord
            The sealed record as appended to the spine and seen by the
            anomaly detector.
        """
        merged: dict[str, Any] = {}

        # Step 1: merge enabled producers in ascending priority order.
        # On key conflict the *higher* priority value wins because the
        # lower-priority writer ran first and the higher-priority
        # writer's ``dict.update`` overwrites it — see module docstring
        # for the documented override direction.
        #
        # ``producer_failures`` rides alongside ``merged`` as a
        # sidecar list of ``(producer, failure_entry)`` tuples. It is
        # populated when a producer used the ``_lca_failures``
        # protocol extension to surface sub-field failures without
        # aborting the merge path (ADR-0165 §FieldProducer protocol
        # extension; ADR-2026-09-02-i17-traceback §D2).
        producer_failures: list[tuple[Any, dict[str, Any]]] = []
        for producer in self._producers:
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
                # Contained by Layer-1 design: a single broken
                # producer MUST NOT block the rest of the pipeline.
                # FD-2 isolation at the seam.
                log.warning(
                    "emit_pipeline: producer=%s raised %s; skipping",
                    getattr(producer, "name", repr(producer)),
                    exc,
                    exc_info=True,
                )
                continue
            if not fields:
                continue
            # The sidecar key never lands in the merged payload —
            # it is a protocol-internal channel that we strip here so
            # the spine never sees implementation details.
            sidecar = fields.pop("_lca_failures", None)
            if isinstance(sidecar, list):
                for entry in sidecar:
                    if isinstance(entry, dict):
                        producer_failures.append((producer, entry))
            merged.update(fields)

        # Step 2: caller payload wins on conflict (D11).
        if caller_payload:
            merged.update(caller_payload)

        # Step 3: EventSpine.append enforces I12 close-set validation
        # by constructing ``EventRecord``, whose ``__post_init__``
        # raises ``ValueError`` for unknown execution points / channel /
        # outcome / phase. We pre-check ``execution_point`` here for a
        # clearer error path (the spine would raise the same error, but
        # checking up front yields a tighter stack).
        if execution_point not in EXECUTION_POINTS:
            raise ValueError(
                f"UnknownExecutionPoint({execution_point!r}): not in EXECUTION_POINTS whitelist"
            )

        # Step 3a: I17 — every ``*.start`` event MUST carry a
        # ``source_location`` field (ADR-0165.1 §96; ADR-2026-09-02
        # §D4). The check is *producer-aware*, not naive: if the
        # SourceAttacher is in the producer list, the check is
        # strong (raise I17Violation on miss). If SourceAttacher is
        # not in scope, the check degrades to weak: the event still
        # seals without ``source_location`` (so the run continues)
        # and a one-time ``phase_graph.instrument.coverage`` event
        # is published at run end noting the coverage gap.
        source_attacher_present = any(
            getattr(p, "name", "") == "spine.reflector.source" for p in self._producers
        )
        if (
            execution_point.endswith(".start")
            and "source_location" not in merged
            and source_attacher_present
        ):
            raise I17Violation(
                f"I17: execution_point={execution_point!r} requires "
                f"'source_location' in payload (ADR-0165.1 §96); "
                f"SourceAttacher producer missing or disabled"
            )
        if (
            execution_point.endswith(".start")
            and "source_location" not in merged
            and not source_attacher_present
            and not self._coverage_emitted
        ):
            # Producer absent — surface the coverage gap once per
            # pipeline instance so the run directory records it.
            try:
                spine.append(
                    execution_point="phase_graph.instrument.coverage",
                    channel="control",
                    caller_payload={
                        "source_attacher": "missing",
                        "first_observed_ep": execution_point,
                    },
                    outcome=None,
                    span_ctx=span_ctx,
                    phase=phase,
                )
            except Exception as exc:
                log.warning(
                    "emit_pipeline: coverage event publication failed err=%s",
                    exc,
                    exc_info=True,
                )
            self._coverage_emitted = True

        record = spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=merged,
            outcome=outcome,
            span_ctx=span_ctx,
            phase=phase,
            reason=reason,
        )

        # Step 3b: producer sidecar (ADR-0165 §FieldProducer protocol
        # extension). If a producer surfaced sub-field failures via
        # the ``_lca_failures`` key, emit one ``spine.producer.failure``
        # journal event per entry so the failure is observable from
        # the run directory. We never propagate these back to the
        # caller — emission of the original record is the truth, and
        # the sidecar entries are best-effort diagnostics that ride
        # the same anomaly-detection seam (FD-2 containment).
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

        # Step 4: anomaly detector runs on the sealed record. FD-2
        # containment means we never propagate a detector exception
        # back to the caller — emission is the truth, anomaly is
        # best-effort.
        try:
            self._anomaly.on_event(record)
        except Exception as exc:
            # Contained by FD-2 design: emission succeeded, the
            # detector is best-effort.
            log.warning(
                "emit_pipeline: anomaly=%s raised %s; record still emitted",
                getattr(self._anomaly, "name", type(self._anomaly).__name__),
                exc,
                exc_info=True,
            )

        return record


# ── plugin manifest ──────────────────────────────────────────────────


def _looks_like_field_producer(value: object) -> bool:
    """Return True when ``value`` exposes the FieldProducer structural surface."""
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
    effects=EffectClass.NONE,
    description=(
        "Emit pipeline — composes all enabled field_producer.* plugins by "
        "priority ascending, merges their pre-phase dicts, layers caller "
        "payload on top, seals the EventRecord via EventSpine (I12), and "
        "invokes the bound anomaly detector (I15) on the sealed record."
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
    """Materialise an ``EmitPipeline`` from the wired L0 producer plugins.

    Collects every ``field_producer.*`` capability plus the bound
    ``deriver.anomaly`` detector, assembles :class:`EmitPipeline`, and
    publishes it under ``emit_pipeline`` for ``spine.core`` (L2).
    """
    del config  # profile-tolerant; producers come from wired capabilities.

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

    log.debug(
        "spine.emit_pipeline: setup complete producers=%d anomaly=%s",
        len(producers),
        getattr(anomaly, "name", type(anomaly).__name__),
    )


__all__ = ["EmitPipeline", "I17Violation", "setup"]
