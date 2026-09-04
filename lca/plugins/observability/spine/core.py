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
    the ``event_spine`` capability. Two canonical surfaces:

    * ``spine_core.event_spine.append(...)`` — preferred; routes
      through the bound :class:`EmitPipeline` + :class:`FileSink`
      exactly as assembled by :func:`setup`.
    * ``spine_core.append(**kwargs)`` — SpineLike shim; delegates to
      ``event_spine.append`` so callers holding the holder (instead of
      the inner spine) still satisfy the ``SpineLike`` Protocol used by
      ``writable.matrix.assembly``. New code SHOULD use the explicit
      ``.event_spine`` surface.

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

    def append(self, **kwargs: Any) -> Any:
        """SpineLike shim — delegate to the inner :class:`EventSpine`.

        Exists so :class:`lca.infrastructure.observability.writable_matrix.SpineEmitter`
        can ``bind(spine_core)`` directly. The canonical surface for
        new code is :attr:`event_spine`; this shim only forwards.
        """
        return self.event_spine.append(**kwargs)

    def close(self) -> None:
        """Close the sink; the spine itself is stateless across runs.

        Mirrors :meth:`EventSpine.close` so plugin dispose can defer
        the flush + close to the same call. The pipeline has no
        resources to release.
        """
        self.event_spine.close()


# ── plugin manifest ──────────────────────────────────────────────────


# ADR-0167 D11 / I-MV3: deriver 都是 per-run 的(run_dir / agent_role / 写
# journal.json / narrative.md); 不应在 spine.core boot 阶段硬 subscribe。
# transport 在 RunSessionBuilder.build 阶段构造 + subscribe(通过
# SpineCore.event_spine.subscribe)。
#
# COMPAT(delete-when: ADR-0186 PR-3g 全部 deriver subscribe 迁完,
#        tracking: ADR-0186 PR-3g)
# PR-3g subscribe 站点清单(全部在 builder.py):
#   1. step_tree_deriver.on_event — builder.py:215(已有 fold 替代)
#   2. live_tail — SSE 实时路径,暂保留 subscribe,Session observer 迁完删除
#   3. narrative / graph / waterfall / otel_trace — 仅 capability 注册,
#      未在 builder 硬 subscribe;PR-3g 收口改为 snapshot fold
#   4. anomaly — EmitPipeline 直接调用(不经 subscribe);PR-3g 迁 snapshot scan

# Reflector modules that keep a process-local ``_active_spine`` for emit_*.
# Soft-import so a partial profile without those plugins still boots.
_REFLECTOR_SET_ACTIVE_MODULES: tuple[str, ...] = (
    "lca.plugins.observability.spine.reflectors.runtime",
    "lca.plugins.observability.spine.reflectors.cognition",
    "lca.plugins.observability.spine.reflectors.body_llm",
    "lca.plugins.observability.spine.reflectors.agent_spawn",
)


def _activate_process_local_spine(ctx: PluginContext, event_spine: EventSpine) -> None:
    """Wire wrap_instrument + known reflectors to the composed EventSpine.

    Registers a disposer via ``ctx.effect`` when available so profile
    unload clears the process-local accessors (mirrors file_sink close).
    """
    from lca.harness.declarative.compile.instrument_wrap import (
        set_active_spine_accessor,
    )

    previous = set_active_spine_accessor(lambda: event_spine)
    previous_reflectors: list[tuple[Any, Any]] = []
    import importlib

    for module_path in _REFLECTOR_SET_ACTIVE_MODULES:
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            continue
        setter = getattr(module, "set_active_spine", None)
        getter = getattr(module, "get_active_spine", None)
        if not callable(setter):
            continue
        prior = getter() if callable(getter) else None
        setter(event_spine)
        previous_reflectors.append((setter, prior))

    def _restore() -> None:
        set_active_spine_accessor(previous)
        for setter, prior in previous_reflectors:
            setter(prior)

    effect = getattr(ctx, "effect", None)
    if callable(effect):
        effect(_restore, label="spine.core:deactivate_spine_accessor")
        return
    inner = getattr(ctx, "_AuditedPluginContext__inner", None)
    inner_effect = getattr(inner, "effect", None) if inner is not None else None
    if callable(inner_effect):
        inner_effect(_restore, label="spine.core:deactivate_spine_accessor")


@plugin(
    id="spine.core",
    provides=("event_spine", "spine_context"),
    requires=("emit_pipeline", "file_sink"),
    layer="L2",
    kind=PluginKind.SEAM,
    effects="none",
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
    console_sink = (
        getattr(ctx, "soft_get", lambda _k: None)("console_sink")
        if hasattr(ctx, "soft_get")
        else None
    )
    if console_sink is not None and isinstance(console_sink, EventSink):
        sinks.append(console_sink)

    event_spine = EventSpine(sinks=sinks)

    spine_core = SpineCore(
        event_spine=event_spine,
        file_sink=file_sink,
        emit_pipeline=emit_pipeline,
    )

    ctx.provide("event_spine", spine_core)
    ctx.provide("spine_context", SpineContext)

    # ADR-0165.1: publish is not enough — wrap_instrument and reflectors
    # resolve the process-local accessor. Without this, every emit is a
    # silent no-op even though FileSink is mounted.
    _activate_process_local_spine(ctx, event_spine)

    log.debug(
        "spine.core: setup complete pipeline=%s sink=%s",
        getattr(emit_pipeline, "__class__", type(emit_pipeline)).__name__,
        getattr(file_sink, "__class__", type(file_sink)).__name__,
    )


__all__ = ["SpineCore", "setup"]
