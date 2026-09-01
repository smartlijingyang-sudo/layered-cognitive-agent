"""``spine.reflector.signature`` — D11 signature auto-source FieldProducer.

Task 7.1: the first concrete implementation of the
``FieldProducer`` Protocol (``lca.contracts.observability.spine.producer``).

The producer contributes four keys into ``EventRecord.payload`` while
the spine's ``EmitPipeline`` assembles an event:

- ``signature_fingerprint`` — ``sha256(qualname + source)`` of ``fn``
- ``input_params``         — ``str((args, kwargs))`` for the live call
- ``output_schema``         — ``typing.get_type_hints(fn)``
- ``docstring_captured``    — first non-empty line of ``fn.__doc__``

These satisfy D11 (ADR-0165 §11): every emitted event MUST carry
enough auto-source fields to be audit-grade without business code.

Plugin
------
Manifest: ``@plugin(id="spine.reflector.signature",
provides=("field_producer.signature",), layer="L0", kind=PluginKind.SEAM)``.
Provides the ``field_producer.signature`` capability so
``EmitPipeline`` can fetch and merge this producer at boot.
"""

from __future__ import annotations

import hashlib
import inspect
import typing
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

_FINGERPRINT_ALGO = hashlib.sha256


class SignatureFieldProducer:
    """D11 signature FieldProducer — injects 4 audit-grade keys per call.

    Attributes
    ----------
    name:
        Stable identifier used by ``EmitPipeline`` for debug logging
        and assembly-order reporting. Pin to ``"spine.reflector.signature"``
        so it matches the plugin manifest id.
    priority:
        Sort key for the merge pipeline. Higher-priority producers
        (lower numbers) override later writers on key conflict. ``100``
        leaves room above for trace/error producers that need to win
        on conflict.
    enabled:
        Profile-level toggle. ``EmitPipeline`` skips disabled producers
        without removing them from the registry.
    """

    name: str = "spine.reflector.signature"
    priority: int = 100
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
        """Return the four D11 signature fields for the live call.

        The ``phase`` argument is part of the ``FieldProducer`` Protocol
        surface; this producer is phase-agnostic and returns the same
        four keys regardless of phase. The argument is accepted (not
        consumed) so the signature matches the Protocol and so future
        revisions can differentiate by phase without re-decorating.
        """
        del ctx, span, phase  # documented unused; consumed by other producers

        source = inspect.getsource(fn)
        qualname = getattr(fn, "__qualname__", repr(fn))
        fingerprint = _FINGERPRINT_ALGO(
            f"{qualname}\n{source}".encode()
        ).hexdigest()

        return {
            "signature_fingerprint": fingerprint,
            "input_params": str((args, kwargs)),
            "output_schema": typing.get_type_hints(fn),
            "docstring_captured": _first_doc_line(fn.__doc__),
        }


def _first_doc_line(doc: str | None) -> str:
    """Return the first non-empty stripped line of ``doc`` (or ``""``).

    The ``inspect.getsource`` call in :meth:`SignatureFieldProducer.produce`
    raises ``OSError`` if the function is built-in; ``doc`` may be
    ``None`` for runtime-defined callables. Both cases collapse to an
    empty string so the producer never raises inside the merge path.
    """
    if not doc:
        return ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


@plugin(
    id="spine.reflector.signature",
    provides=("field_producer.signature",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "Signature FieldProducer — injects D11 signature_fingerprint, "
        "input_params, output_schema, docstring_captured into every "
        "spine EventRecord.payload via EmitPipeline merge."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_reflector_signature",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_source",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.signature",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline",),
        emits=("field_producer.signature",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Register a singleton ``SignatureFieldProducer`` instance.

    The plugin carries no I/O, no state, and no startup work beyond
    ``ctx.provide``; the ``L0`` layer is sufficient because every
    profile that wants D11 coverage just declares this plugin in its
    enables list.
    """
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.signature", SignatureFieldProducer())


__all__ = ["SignatureFieldProducer", "setup"]
