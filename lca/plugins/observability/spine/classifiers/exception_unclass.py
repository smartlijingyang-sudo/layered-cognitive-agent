"""``spine.classifier.exception.unclass`` — Layer-C fallback exception classifier.

Task 7.5 (ADR-0165.1 §7.5.4): the second ``FieldProducer`` in the
exception-classifier chain. It runs after
``spine.classifier.exception.builtin`` (Layer-A) and catches every
exception the Layer-A ``BUILTIN_MAP`` could not classify.

Per ADR-0165 / ADR-0165.1 §7.5.4, this producer is the open-domain
detector (Layer-C): it cannot know up front which exception types it
will see, so it learns them at runtime. Each unique exception class
is recorded in an in-memory ``_seen_signatures`` index keyed by
``exception_class``. On the third occurrence of the same class, the
producer escalates ``recommended_action`` to
``"add_to_BUILTIN_MAP"`` — the operator signal to promote the class
into the Layer-A table.

Emitted fields
--------------
``produce(phase="exception", ctx.current_exception=...)`` returns:

- ``outcome``            — always ``"unclassified"``.
- ``edge_case_id``       — always ``"UnclassifiedError"``.
- ``exception_class``    — ``type(exc).__name__``.
- ``first_seen``         — ``True`` on the first hit, ``False`` after.
- ``recommended_action`` — ``"track_more"`` until the third hit,
  then ``"add_to_BUILTIN_MAP"`` for all subsequent calls.

Lookup semantics
----------------
Counts are keyed by ``type(exc).__name__`` (string) rather than the
type object so the index survives interpreter-level changes (e.g.
``os.fork`` without ``exec``, GC of unreferenced types). The key is
collision-free for any user-defined exception because Python enforces
unique ``__name__`` per class object per module.

State isolation
---------------
The ``_seen_signatures`` counter lives on the producer instance, not
in a module-level global. Tests construct a fresh ``UnclassClassifier``
per test (see ``tests/lca_plugins/observability/spine/test_classifier_unclass.py``)
so per-class counts cannot bleed between cases.

Plugin manifest
---------------
``@plugin(id="spine.classifier.exception.unclass",
provides=("field_producer.exception.unclass",), layer="L0",
kind=PluginKind.SEAM)``. ``priority=99`` makes it the last producer
in the ``EmitPipeline`` merge order — by ADR-0165.1 §7.5.4 it is the
fallback that runs after Layer-A's ``ExceptionBuiltinClassifier``.
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ── escalation threshold ────────────────────────────────────────────
#
# After this many occurrences of the same exception class, the producer
# promotes ``recommended_action`` from ``"track_more"`` to
# ``"add_to_BUILTIN_MAP"``. The threshold is fixed at 3 per
# ADR-0165.1 §7.5.4 (spec wording: "3 次重复后自动建议入 BUILTIN_MAP").
_ESCALATION_THRESHOLD: int = 3


class UnclassClassifier:
    """Layer-C FieldProducer — fallback for unmapped exceptions.

    Attributes
    ----------
    name:
        Stable identifier matching the plugin manifest id. Used by
        ``EmitPipeline`` for debug logging and merge-order reporting.
    priority:
        ``99`` so this producer runs last in the ``EmitPipeline``
        merge order — by ADR-0165.1 §7.5.4 it is the fallback that
        runs after Layer-A's ``ExceptionBuiltinClassifier``.
    enabled:
        Profile-level toggle. ``EmitPipeline`` skips disabled
        producers without removing them from the registry.
    """

    name: str = "spine.classifier.exception.unclass"
    priority: int = 99
    enabled: bool = True

    def __init__(self) -> None:
        # Instance-scoped counter index keyed by ``exception_class``
        # (string). Tests construct a fresh producer per case so
        # cross-test pollution cannot leak through this dict.
        self._seen_signatures: dict[str, int] = {}

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
        """Return the ``UnclassifiedError`` envelope for unmapped exceptions.

        On the first hit for a class: ``first_seen=True``,
        ``recommended_action="track_more"``. After the third hit, every
        subsequent call sets ``recommended_action="add_to_BUILTIN_MAP"``.

        Non-``"exception"`` phases and a ``ctx`` without
        ``current_exception`` return ``{}`` (no contribution).
        """
        del fn, args, kwargs, span  # not consumed; required by the Protocol surface.

        if phase != "exception":
            return {}

        exc = _current_exception(ctx)
        if exc is None:
            return {}

        exc_class_name = type(exc).__name__
        seen_count = self._seen_signatures.get(exc_class_name, 0) + 1
        self._seen_signatures[exc_class_name] = seen_count

        return {
            "outcome": "unclassified",
            "edge_case_id": "UnclassifiedError",
            "exception_class": exc_class_name,
            "first_seen": seen_count == 1,
            "recommended_action": (
                "add_to_BUILTIN_MAP" if seen_count >= _ESCALATION_THRESHOLD else "track_more"
            ),
        }


def _current_exception(ctx: Any) -> BaseException | None:
    """Return ``ctx.current_exception`` if available, else ``None``.

    The ``FieldProducer`` Protocol types ``ctx`` as ``Any``; the
    spine contract (ADR-0165 / ADR-0165.1 §7.5.2) is that producers
    read ``ctx.current_exception`` during the ``"exception"`` phase.
    Tests and stubs may pass any object exposing the attribute;
    production wiring via ``wrap_instrument`` sets it before the
    producer runs.
    """
    if ctx is None:
        return None
    current = getattr(ctx, "current_exception", None)
    if isinstance(current, BaseException):
        return current
    return None


@plugin(
    id="spine.classifier.exception.unclass",
    provides=("field_producer.exception.unclass",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "Layer-C fallback FieldProducer — catches every exception the "
        "Layer-A BUILTIN_MAP cannot classify, emits UnclassifiedError "
        "envelope, and escalates recommended_action to "
        "add_to_BUILTIN_MAP after 3 occurrences of the same class."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_classifier_unclass",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.classify",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.exception_unclass",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline",),
        emits=("field_producer.exception_unclass",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Register a singleton ``UnclassClassifier`` instance.

    The plugin carries no I/O, no startup work beyond ``ctx.provide``,
    and no module-level state; the ``L0`` layer is sufficient because
    every profile that wants Layer-C exception fallback just declares
    this plugin in its enables list.
    """
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.exception.unclass", UnclassClassifier())


__all__ = [
    "UnclassClassifier",
    "setup",
]
