"""``spine.spantree`` plugin — D11 spantree auto-source (I13).

Per ADR-0165.1 §7.5.5, this plugin contributes the earliest
:class:`~lca.contracts.observability.spine.producer.FieldProducer` in
the ``EmitPipeline`` merge (``priority=5``). It stamps the span
identity and causality metadata every other producer and every
downstream consumer relies on:

- ``span_id`` / ``parent_span_id`` — read from the active span (the
  ``span`` argument, else the top of the ``SpineContext`` span stack).
- ``sequence`` / ``epoch`` — minted from the run-scoped monotonic
  counters on :class:`SpineContext`.
- ``prev_event_hash`` — the current head of the ``SpineContext`` hash
  chain, i.e. the hash of the previous event in this run.

Phase machine ownership
-----------------------
The I13 phase machine (``end`` execution point must match the ``start``
that opened the span) is enforced by ``SpineContext.push_span`` /
``pop_span``. This producer is a pure reader: it never pushes, pops, or
mutates the span stack, so the check has exactly one owner. Callers
(``wrap_instrument`` in a later PR) bracket the instrumented function
with push/pop and pass the resulting span in.

Wiring
------
:func:`setup` publishes the singleton under the
``field_producer.spantree`` capability; the spine's ``EmitPipeline``
fetches it via ``ctx.require("field_producer.spantree")`` and merges its
fields first, so higher-priority producers can never overwrite span
identity.
"""

from __future__ import annotations

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
from lca.contracts.observability.spine.producer import Phase
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.context import SpineContext


class SpanTreeFieldProducer:
    """Auto-source for span identity + causality counters (D11 / I13).

    ``priority=5`` places this producer ahead of the signature (10) and
    context (20) axes: on key conflict the earlier writer wins, so span
    identity is authoritative.
    """

    name: str = "spine.spantree"
    priority: int = 5
    enabled: bool = True

    def produce(
        self,
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: Phase,
    ) -> dict[str, Any]:
        """Return span identity plus freshly minted causality counters.

        ``phase`` ``"pre"`` and ``"post"`` both contribute the full field
        set — the start and end events of one execution point each carry
        their own ``sequence`` / ``epoch``. The ``"exception"`` phase
        contributes nothing; that envelope belongs to the classifier
        producers (ADR-0165.1 §7.5.2/4), which run on the same event as
        a ``"post"`` merge and therefore already carry span identity.
        """
        del fn, args, kwargs, ctx  # not consumed; required by the Protocol surface

        if phase not in ("pre", "post"):
            return {}

        span_id, parent_span_id = _span_identity(span)
        return {
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "sequence": SpineContext.next_sequence(),
            "epoch": SpineContext.next_epoch(),
            "prev_event_hash": SpineContext.last_hash(),
        }


def _span_identity(span: Any) -> tuple[str | None, str | None]:
    """Resolve ``(span_id, parent_span_id)`` for the active span.

    An explicit ``span`` wins over the stack top so callers can stamp a
    detached span (e.g. a span captured before an ``await`` boundary).
    With neither an explicit span nor a non-empty stack the identity is
    ``(None, None)``: the producer must never raise inside the merge
    path, and ``EventRecord`` assembly supplies its own fallback.
    """
    active = span if span is not None else SpineContext.current_span()
    if active is None:
        return None, None
    span_id = getattr(active, "span_id", None)
    parent_span_id = getattr(active, "parent_span_id", None)
    return span_id, parent_span_id


@plugin(
    id="spine.spantree",
    provides=("field_producer.spantree",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "SpanTree FieldProducer — injects D11 span_id / parent_span_id / "
        "sequence / epoch / prev_event_hash into every spine "
        "EventRecord.payload. Runs first (priority 5) so span identity "
        "wins the EmitPipeline merge; reads the I13 phase machine owned "
        "by SpineContext without mutating it."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_spantree",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_span_context",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.spantree",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline", "spine_context"),
        emits=("field_producer.spantree",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Register a singleton ``SpanTreeFieldProducer`` instance."""
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.spantree", SpanTreeFieldProducer())


__all__ = ["SpanTreeFieldProducer", "setup"]
