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
from typing import Any, Protocol, runtime_checkable

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
            if fields:
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
        # ``source_location`` field (ADR-0165.1 §96). Check happens
        # after the producer + caller_payload merge so a
        # ``source_location`` injected by either side satisfies the
        # invariant; raising here keeps non-compliant emissions out of
        # the spine entirely (fail-fast at the seam).
        if execution_point.endswith(".start") and "source_location" not in merged:
            raise I17Violation(
                f"I17: execution_point={execution_point!r} requires "
                f"'source_location' in payload (ADR-0165.1 §96); "
                f"SourceAttacher producer missing or disabled"
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


@plugin(
    id="spine.emit_pipeline",
    provides=("emit_pipeline",),
    requires=("field_producer.*",),
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
        reads=("field_producer.*", "spine.deriver.anomaly"),
        emits=("emit_pipeline",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Materialise an ``EmitPipeline`` from the wired L0 producer plugins.

    The plugin reads the bound ``spine.deriver.anomaly`` capability
    (provided by Task 7.7) plus every ``field_producer.*`` capability
    from the profile, sorts them, and publishes the assembled pipeline
    under the ``emit_pipeline`` capability so ``spine.core`` (L2) can
    fetch it.

    The config schema is profile-driven; this setup accepts both an
    explicit ``producers`` list and the implicit "all wired
    field_producer.*" default. Unknown keys are ignored — the plugin
    is config-tolerant by design so adding new producer plugins does
    not require editing every existing profile.

    Task 7.8 publishes the ``EmitPipeline`` class; the live boot wiring
    is delivered by PR-8 (spine.core), so this setup raises a
    ``NotImplementedError`` until that PR lands. Tests instantiate
    ``EmitPipeline`` directly and do not invoke setup.
    """
    del ctx, config  # accepted for protocol conformance; deferred to PR-8.
    raise NotImplementedError(
        "spine.emit_pipeline.setup is wired by PR-8 (spine.core); Task 7.8 "
        "publishes the class so PR-8 can declare() it. Tests inject "
        "EmitPipeline directly without going through setup."
    )


__all__ = ["EmitPipeline", "I17Violation", "setup"]
