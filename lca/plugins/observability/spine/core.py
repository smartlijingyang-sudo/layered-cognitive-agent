"""``spine.core`` — L2 composer plugin (PR-8 / spec §7.6.1).

Wires the canonical :class:`EventSpine` for one run: the assembled
:class:`EmitPipeline` is the field-merge source, the bound
:class:`FileSink` is the append-only truth sink, and the
:class:`SpineContext` (process-local ContextVar stack) is published as
the ``spine_context`` capability so other plugins can read the active
span / run / step without re-discovering it.

Layering
--------
- ``L2`` (this plugin): produces ``event_spine`` and ``spine_context``.
- ``L1`` (spine.emit_pipeline): produces ``emit_pipeline``.
- ``L0`` producers / classifiers / derivers / sink.file: assemble the
  field producer list and the disk sink.

Per ADR-0165 / ADR-0165.1 §7.6.1, ``spine.core`` is the single boot
DAG node that owns ``EventSpine`` construction; everything downstream
consumes the capability via ``ctx.require("event_spine")``.

Module contract
---------------
- Public symbols: ``SpineCore``, ``setup``.
- ``SpineCore`` is a thin holder of ``(event_spine, file_sink,
  emit_pipeline)`` plus the constructor wiring. The publish-capability
  path lives in :func:`setup`.
- The plugin does NOT own the field producer list — that is the
  ``EmitPipeline``'s responsibility. It just hands the pipeline to
  ``EventSpine`` so each emit walks the merge path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

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
from lca.contracts.protocols.declarative.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import (
    EffectClass,
    PluginContext,
    PluginKind,
    plugin,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.base import EventSink

log = logging.getLogger(__name__)


# ── core holder ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SpineCore:
    """Holder for the L2-composed spine surface of one run.

    The class is the public seam that downstream plugins consume via
    the ``event_spine`` capability — they call
    ``spine_core.event_spine.append(...)`` and the wire goes through
    the bound ``EmitPipeline`` + ``FileSink`` exactly as assembled by
    :func:`setup`.

    Attributes
    ----------
    event_spine:
        The :class:`EventSpine` instance. Single source of truth per
        run; ``EventSpine.append`` enforces I12 close-set semantics.
    file_sink:
        The :class:`FileSink` (or any :class:`EventSink` for tests)
        that backs ``event_spine``. Held so the plugin can ``close``
        the sink on dispose without rebuilding the spine.
    emit_pipeline:
        The :class:`EmitPipeline` assembled by ``spine.emit_pipeline``.
        Stashed for diagnostics — the merge path runs inside
        ``EventSpine.append`` only when callers route through the
        pipeline (which they do via ``emit_pipeline.emit``).
    """

    event_spine: EventSpine
    file_sink: EventSink
    emit_pipeline: Any

    def close(self) -> None:
        """Close the sink; the spine itself is stateless across runs.

        Mirrors :meth:`EventSpine.close` so plugin dispose can defer
        the flush + close to the same call. The pipeline has no
        resources to release.
        """
        self.event_spine.close()


# ── plugin manifest ──────────────────────────────────────────────────


_OPTIONAL_DERIVER_KEYS: tuple[str, ...] = (
    "step_tree",
    "narrative",
    "graph",
    "live_tail",
)


def _soft_get(ctx: PluginContext, key: str) -> Any | None:
    """Return an optional capability when the context supports soft lookup."""
    soft_get = getattr(ctx, "soft_get", None)
    if callable(soft_get):
        return soft_get(key)
    return None


@plugin(
    id="spine.core",
    provides=("event_spine", "spine_context"),
    requires=("emit_pipeline", "file_sink"),
    layer="L2",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "L2 spine composer — assembles EventSpine from the bound "
        "EmitPipeline (field merge) and FileSink (append-only truth), "
        "publishes event_spine + spine_context so downstream plugins "
        "and the wrap_instrument family route through one entry point."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_core",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_source",)),
        observability=EvidenceContract(
            descriptors=("spine.event_spine", "spine.spine_context"),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline", "file_sink"),
        emits=("event_spine", "spine_context"),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Materialise the run's :class:`SpineCore` from the wired capabilities.

    Requires the ``emit_pipeline`` capability (from
    ``spine.emit_pipeline``, L1) and the ``file_sink`` capability
    (from ``spine.sink.file``, L0). Both are resolved via the Cordis
    DAG; if either is missing, setup raises and the profile fails to
    boot — a misconfigured profile must never silently fall back to a
    no-op spine (I4: single entrypoint for framework events).

    Optional derivers (``step_tree``, ``narrative``, ``graph``,
    ``live_tail``) and ``console_sink`` are soft-looked-up: when present
    they are subscribed / appended without failing partial profiles.

    The assembled :class:`EventSpine` is published under
    ``event_spine``; the process-local :class:`SpineContext` class
    itself is published under ``spine_context`` (the ContextVars are
    module-level and live for the lifetime of the process, so the
    "value" we publish is the class object — consumers read
    ``spine_context.current_span()`` and friends).
    """
    del config  # accepted for protocol conformance; this plugin is config-free.

    emit_pipeline = ctx.require("emit_pipeline")
    file_sink = ctx.require("file_sink")

    sinks: list[EventSink] = [file_sink]
    console_sink = _soft_get(ctx, "console_sink")
    if console_sink is not None and isinstance(console_sink, EventSink):
        sinks.append(console_sink)

    event_spine = EventSpine(sinks=sinks)

    for deriver_key in _OPTIONAL_DERIVER_KEYS:
        deriver = _soft_get(ctx, deriver_key)
        on_event = getattr(deriver, "on_event", None) if deriver is not None else None
        if callable(on_event):
            event_spine.subscribe(on_event)

    spine_core = SpineCore(
        event_spine=event_spine,
        file_sink=file_sink,
        emit_pipeline=emit_pipeline,
    )

    ctx.provide("event_spine", spine_core)
    ctx.provide("spine_context", SpineContext)

    log.debug(
        "spine.core: setup complete pipeline=%s sink=%s",
        getattr(emit_pipeline, "__class__", type(emit_pipeline)).__name__,
        getattr(file_sink, "__class__", type(file_sink)).__name__,
    )


__all__ = ["SpineCore", "setup"]
