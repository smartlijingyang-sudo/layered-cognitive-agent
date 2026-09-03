"""``spine.classifier.exception.builtin`` — Layer-A known exception classifier.

Task 7.4 (ADR-0165.1 §7.5.2): the first concrete ``FieldProducer`` that
classifies a raised exception against ~60 stdlib exception types and
emits ``(outcome, edge_case_id)`` into ``EventRecord.payload`` during
the ``exception`` phase.

The producer is "Layer-A known": every well-known stdlib exception
type has a stable ``(outcome, edge_case_id)`` pair. Anything outside
``BUILTIN_MAP`` returns ``{}`` and falls through to
``spine.classifier.exception.unclass`` (Layer-C fallback, Task 7.5).

Lookup semantics
----------------
``BUILTIN_MAP`` keys are exact exception types. When the raised
exception's type is a user-defined subclass, the producer walks
``type(exc).__mro__`` (skipping the leaf class itself) and matches
the first mapped ancestor. This lets downstream code raise specialised
subclasses (``class _DomainTimeout(TimeoutError): ...``) and still
benefit from the standard outcome taxonomy. The emitted
``exception_class`` is always ``type(exc).__name__`` so callers can
distinguish the leaf type from its classification ancestor.

Plugin manifest
---------------
``@plugin(id="spine.classifier.exception.builtin",
provides=("field_producer.exception.builtin",), layer="L0",
kind=PluginKind.SEAM)``. Provides the
``field_producer.exception_builtin`` capability so the spine's
``EmitPipeline`` can fetch this producer at boot.
"""

from __future__ import annotations

import argparse
import asyncio
import builtins
import configparser
import http.client
import json
import multiprocessing
import pickle
import queue
import threading
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

# ── builtin exception map ───────────────────────────────────────────
#
# Maps stdlib ``BaseException`` subclasses to ``(outcome, edge_case_id)``
# tuples. ``outcome`` is a closed vocabulary matching the
# ``EventRecord.outcome`` type (see ``lca.infrastructure.observability.
# spine.event_record``). ``edge_case_id`` is a short, stable identifier
# used for grouping and anomaly correlation (I15 / ADR-0165.1 §7.5.2).
#
# Note on ordering: lookup is exact-type-first, then MRO walk, so the
# dict order does not matter for correctness. ``TimeoutError`` is a
# subclass of ``OSError`` on Python 3.11+; both are listed so the MRO
# walk produces the most-specific outcome for each.
BUILTIN_MAP: dict[type[BaseException], tuple[str, str]] = {
    # ── cancellation / timeout ──────────────────────────────────────
    asyncio.TimeoutError: ("timeout", "Timeout"),
    asyncio.CancelledError: ("cancelled", "Cancel"),
    builtins.TimeoutError: ("timeout", "Timeout"),
    multiprocessing.TimeoutError: ("timeout", "MultiprocessingTimeout"),
    # ── value / type / arithmetic ───────────────────────────────────
    ValueError: ("invalid_value", "Value"),
    TypeError: ("invalid_type", "Type"),
    ArithmeticError: ("arithmetic", "Arithmetic"),
    FloatingPointError: ("arithmetic", "FloatingPoint"),
    OverflowError: ("overflow", "Overflow"),
    ZeroDivisionError: ("arithmetic", "ZeroDivision"),
    # ── lookup / attribute ──────────────────────────────────────────
    KeyError: ("not_found", "Key"),
    IndexError: ("out_of_range", "Index"),
    AttributeError: ("missing_attribute", "Attribute"),
    NameError: ("missing_name", "Name"),
    UnboundLocalError: ("missing_name", "UnboundLocal"),
    LookupError: ("not_found", "Lookup"),
    # ── OS / IO / filesystem ────────────────────────────────────────
    # ``IOError`` is an alias of ``OSError`` since Python 3.3 — a single
    # mapping handles both spellings without duplicate keys.
    OSError: ("io_error", "OSError"),
    FileNotFoundError: ("not_found", "FileNotFound"),
    FileExistsError: ("conflict", "FileExists"),
    PermissionError: ("rejected", "PermissionDenied"),
    IsADirectoryError: ("invalid_input", "IsADirectory"),
    NotADirectoryError: ("invalid_input", "NotADirectory"),
    InterruptedError: ("interrupted", "Interrupted"),
    ProcessLookupError: ("not_found", "ProcessLookup"),
    # ── network ─────────────────────────────────────────────────────
    ConnectionError: ("failure", "NetworkUnavailable"),
    ConnectionAbortedError: ("failure", "ConnectionAborted"),
    ConnectionRefusedError: ("rejected", "ConnectionRefused"),
    ConnectionResetError: ("failure", "ConnectionReset"),
    BrokenPipeError: ("failure", "BrokenPipe"),
    # ── runtime / control flow ──────────────────────────────────────
    RuntimeError: ("runtime", "Runtime"),
    NotImplementedError: ("not_implemented", "NotImplemented"),
    RecursionError: ("overflow", "Recursion"),
    MemoryError: ("overflow", "Memory"),
    StopIteration: ("exhausted", "StopIteration"),
    StopAsyncIteration: ("exhausted", "StopAsyncIteration"),
    GeneratorExit: ("cancelled", "GeneratorExit"),
    SystemExit: ("cancelled", "SystemExit"),
    KeyboardInterrupt: ("cancelled", "KeyboardInterrupt"),
    # ── assertion / import / module ─────────────────────────────────
    AssertionError: ("rejected", "Assertion"),
    ImportError: ("failure", "Import"),
    ModuleNotFoundError: ("not_found", "ModuleNotFound"),
    # ── encoding / data ─────────────────────────────────────────────
    UnicodeError: ("invalid_input", "Unicode"),
    UnicodeDecodeError: ("invalid_input", "UnicodeDecode"),
    UnicodeEncodeError: ("invalid_input", "UnicodeEncode"),
    UnicodeTranslateError: ("invalid_input", "UnicodeTranslate"),
    BufferError: ("invalid_input", "Buffer"),
    # ── http-style (stdlib) ─────────────────────────────────────────
    http.client.HTTPException: ("failure", "HTTP"),
    http.client.BadStatusLine: ("invalid_input", "BadStatusLine"),
    http.client.InvalidURL: ("invalid_input", "InvalidURL"),
    http.client.UnknownTransferEncoding: ("invalid_input", "UnknownTransferEncoding"),
    http.client.UnknownProtocol: ("invalid_input", "UnknownProtocol"),
    http.client.UnimplementedFileMode: ("not_implemented", "UnimplementedFileMode"),
    http.client.IncompleteRead: ("exhausted", "IncompleteRead"),
    http.client.RemoteDisconnected: ("failure", "RemoteDisconnected"),
    http.client.ImproperConnectionState: ("failure", "ImproperConnectionState"),
    http.client.NotConnected: ("failure", "NotConnected"),
    http.client.ResponseNotReady: ("invalid_input", "ResponseNotReady"),
    http.client.CannotSendHeader: ("failure", "CannotSendHeader"),
    http.client.CannotSendRequest: ("failure", "CannotSendRequest"),
    http.client.LineTooLong: ("invalid_input", "LineTooLong"),
    # ── argparse / cli ──────────────────────────────────────────────
    argparse.ArgumentError: ("invalid_input", "Argument"),
    argparse.ArgumentTypeError: ("invalid_input", "ArgumentType"),
    # ── json / pickle / configparser ────────────────────────────────
    json.JSONDecodeError: ("invalid_input", "JSONDecode"),
    pickle.UnpicklingError: ("invalid_input", "Unpickling"),
    configparser.Error: ("invalid_input", "ConfigParser"),
    configparser.ParsingError: ("invalid_input", "ConfigParserParsing"),
    configparser.DuplicateOptionError: ("conflict", "ConfigParserDuplicateOption"),
    configparser.DuplicateSectionError: ("conflict", "ConfigParserDuplicateSection"),
    configparser.NoOptionError: ("not_found", "ConfigParserNoOption"),
    configparser.NoSectionError: ("not_found", "ConfigParserNoSection"),
    configparser.InterpolationError: ("invalid_input", "ConfigParserInterpolation"),
    configparser.InterpolationDepthError: (
        "overflow",
        "ConfigParserInterpolationDepth",
    ),
    configparser.InterpolationMissingOptionError: (
        "not_found",
        "ConfigParserInterpolationMissingOption",
    ),
    configparser.InterpolationSyntaxError: (
        "invalid_input",
        "ConfigParserInterpolationSyntax",
    ),
    configparser.MissingSectionHeaderError: (
        "invalid_input",
        "ConfigParserMissingSectionHeader",
    ),
    # ── threading / multiprocessing / queue ─────────────────────────
    threading.ThreadError: ("failure", "Thread"),
    threading.BrokenBarrierError: ("failure", "BrokenBarrier"),
    multiprocessing.ProcessError: ("failure", "Process"),
    multiprocessing.AuthenticationError: ("rejected", "MultiprocessingAuth"),
    multiprocessing.BufferTooShort: ("invalid_input", "BufferTooShort"),
    queue.Empty: ("exhausted", "QueueEmpty"),
    queue.Full: ("rejected", "QueueFull"),
}


# Conditionally add ``BrokenThreadPool`` (Python 3.12+),
# ``queue.ShutDown`` (Python 3.13+), and three ``configparser``
# exceptions (``InvalidWriteError``, ``MultilineContinuationError``,
# ``UnnamedSectionDisabledError`` — added across Python 3.12–3.13).
# All are stdlib exceptions whose existence depends on interpreter
# version; guard with ``getattr`` so the module imports on older
# interpreters AND so mypy does not flag missing stubs.
_BrokenThreadPool = getattr(threading, "BrokenThreadPool", None)
if isinstance(_BrokenThreadPool, type) and issubclass(_BrokenThreadPool, BaseException):
    BUILTIN_MAP[_BrokenThreadPool] = ("failure", "BrokenThreadPool")

_QueueShutDown = getattr(queue, "ShutDown", None)
if isinstance(_QueueShutDown, type) and issubclass(_QueueShutDown, BaseException):
    BUILTIN_MAP[_QueueShutDown] = ("cancelled", "QueueShutDown")

for _name, _outcome, _edge_id in (
    ("InvalidWriteError", "invalid_input", "ConfigParserInvalidWrite"),
    ("MultilineContinuationError", "invalid_input", "ConfigParserMultilineContinuation"),
    ("UnnamedSectionDisabledError", "rejected", "ConfigParserUnnamedSectionDisabled"),
):
    _exc_cls = getattr(configparser, _name, None)
    if isinstance(_exc_cls, type) and issubclass(_exc_cls, BaseException):
        BUILTIN_MAP[_exc_cls] = (_outcome, _edge_id)


class ExceptionBuiltinClassifier:
    """Layer-A FieldProducer — classify stdlib exception types.

    The producer runs only during the ``"exception"`` phase. For
    every other phase (``"pre"`` / ``"post"``) it returns an empty
    dict, deferring to lower-priority producers and the standard
    ``EmitPipeline`` merge.

    Attributes
    ----------
    name:
        Stable identifier matching the plugin manifest id. Used by
        ``EmitPipeline`` for debug logging and merge-order reporting.
    priority:
        ``30`` so this producer runs after ``spine.reflector.signature``
        (``100``) and ``spine.reflector.context`` (``20`` per
        ADR-0165.1 §7.5.3). Lower numbers = higher priority on conflict;
        the chosen value lets context / signature fields win on shared
        keys while leaving room below for trace / budget producers.
    enabled:
        Profile-level toggle. ``EmitPipeline`` skips disabled
        producers without removing them from the registry.
    """

    name: str = "spine.classifier.exception.builtin"
    priority: int = 30
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
        """Return the ``outcome`` / ``edge_case_id`` / ``exception_class`` triplet.

        Lookup order:

        1. ``type(exc)`` exact match in ``BUILTIN_MAP``.
        2. MRO walk starting from the second element (skip the leaf
           class itself, which already failed step 1).
        3. No match → ``{}`` (Layer-C fallback handles the rest).

        ``exception_class`` is always ``type(exc).__name__`` so callers
        see the concrete subclass even when the classification is
        inherited from an ancestor.
        """
        del fn, args, kwargs, span  # not consumed; required by the Protocol surface

        if phase != "exception":
            return {}

        exc = _current_exception(ctx)
        if exc is None:
            return {}

        exc_type = type(exc)
        mapping = BUILTIN_MAP.get(exc_type)
        if mapping is None:
            # MRO walk — find the first mapped ancestor.
            for ancestor in exc_type.__mro__[1:]:
                ancestor_mapping = BUILTIN_MAP.get(ancestor)
                if ancestor_mapping is not None:
                    mapping = ancestor_mapping
                    break
        if mapping is None:
            return {}

        outcome, edge_case_id = mapping
        return {
            "outcome": outcome,
            "edge_case_id": edge_case_id,
            "exception_class": exc_type.__name__,
        }


def _current_exception(ctx: Any) -> BaseException | None:
    """Return ``ctx.current_exception`` if available, else ``None``.

    The ``FieldProducer`` Protocol types ``ctx`` as ``Any``; the spine
    contract (ADR-0165 / ADR-0165.1 §7.5.2) is that producers read
    ``ctx.current_exception`` during the ``"exception"`` phase. Tests
    and stubs may pass any object exposing the attribute; production
    wiring via ``wrap_instrument`` sets it before the producer runs.
    """
    if ctx is None:
        return None
    current = getattr(ctx, "current_exception", None)
    if isinstance(current, BaseException):
        return current
    return None


@plugin(
    id="spine.classifier.exception.builtin",
    provides=("field_producer.exception.builtin",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "Layer-A known-exception FieldProducer — maps ~70 stdlib "
        "exception types to (outcome, edge_case_id) pairs and emits "
        "exception_class. Unknown exceptions yield {} so Layer-C "
        "(spine.classifier.exception.unclass) can take over."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_classifier_builtin",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.classify",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.exception_builtin",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline",),
        emits=("field_producer.exception.builtin",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Register a singleton ``ExceptionBuiltinClassifier`` instance.

    The plugin carries no I/O, no state, and no startup work beyond
    ``ctx.provide``; the ``L0`` layer is sufficient because every
    profile that wants Layer-A exception classification just declares
    this plugin in its enables list.
    """
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.exception.builtin", ExceptionBuiltinClassifier())


__all__ = [
    "BUILTIN_MAP",
    "ExceptionBuiltinClassifier",
    "setup",
]
