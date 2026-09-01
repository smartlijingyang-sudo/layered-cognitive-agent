"""Tests for ``spine.classifier.exception.builtin`` FieldProducer plugin.

Task 7.4 (Layer-A known): the producer classifies ~60 stdlib
exception types into ``(outcome, edge_case_id)`` pairs that the
spine's ``EmitPipeline`` injects into ``EventRecord.payload`` during
the ``exception`` phase.

The minimal contract pinned by this test:

- ``TimeoutError`` → ``outcome="timeout"``, ``edge_case_id="Timeout"``
- ``ValueError`` → ``outcome="invalid_value"``, ``edge_case_id="Value"``
- ``KeyError`` → ``outcome="not_found"``, ``edge_case_id="Key"``
- ``OSError`` → ``outcome="io_error"``, ``edge_case_id="OSError"``

Plus structural checks: Protocol conformance, manifest shape, and
phase-handling (non-``"exception"`` phases must return ``{}``).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer

# ── helpers ──────────────────────────────────────────────────────────


def _ctx_with_exception(exc: BaseException) -> Any:
    """Build a minimal ``ctx`` object carrying ``current_exception``.

    The classifier looks up the raised exception through
    ``ctx.current_exception`` (per the FieldProducer Protocol contract
    documented in ``lca.contracts.observability.spine.producer``);
    tests don't need the full ``SpineContext`` machinery — any object
    with the attribute is acceptable since ``ctx`` is typed as ``Any``.
    """

    class _Ctx:
        current_exception = exc

    return _Ctx()


# ── protocol conformance ─────────────────────────────────────────────


def test_exception_builtin_classifier_satisfies_field_producer_protocol() -> None:
    """``ExceptionBuiltinClassifier`` structurally implements ``FieldProducer``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    assert isinstance(producer, FieldProducer)


def test_exception_builtin_classifier_metadata() -> None:
    """Producer exposes ``name`` / ``priority`` / ``enabled`` seam attrs."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    assert producer.name == "spine.classifier.exception.builtin"
    assert isinstance(producer.priority, int)
    assert producer.enabled is True


# ── canonical mappings (the brief's required cases) ─────────────────


def test_timeout_error_maps_to_timeout_outcome() -> None:
    """``TimeoutError`` MUST yield ``outcome="timeout"`` / ``edge_case_id="Timeout"``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(TimeoutError("boom")),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "timeout"
    assert payload["edge_case_id"] == "Timeout"


def test_value_error_maps_to_invalid_value_outcome() -> None:
    """``ValueError`` MUST yield ``outcome="invalid_value"`` / ``edge_case_id="Value"``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(ValueError("bad value")),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "invalid_value"
    assert payload["edge_case_id"] == "Value"


def test_key_error_maps_to_not_found_outcome() -> None:
    """``KeyError`` MUST yield ``outcome="not_found"`` / ``edge_case_id="Key"``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(KeyError("missing")),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "not_found"
    assert payload["edge_case_id"] == "Key"


def test_os_error_maps_to_io_error_outcome() -> None:
    """``OSError`` MUST yield ``outcome="io_error"`` / ``edge_case_id="OSError"``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(OSError("io")),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "io_error"
    assert payload["edge_case_id"] == "OSError"


# ── exception_class field ───────────────────────────────────────────


def test_exception_class_field_carries_type_name() -> None:
    """The producer MUST emit ``exception_class`` = the type ``__name__``."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(TimeoutError()),
        span=object(),
        phase="exception",
    )

    assert payload["exception_class"] == "TimeoutError"


# ── phase routing ────────────────────────────────────────────────────


def test_non_exception_phase_returns_empty_dict() -> None:
    """``produce(phase="pre"|"post")`` MUST return ``{}`` (no contribution)."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    producer = ExceptionBuiltinClassifier()
    ctx = _ctx_with_exception(TimeoutError())  # would normally contribute

    assert (
        producer.produce(fn=lambda: None, args=(), kwargs={}, ctx=ctx, span=object(), phase="pre")
        == {}
    )
    assert (
        producer.produce(fn=lambda: None, args=(), kwargs={}, ctx=ctx, span=object(), phase="post")
        == {}
    )


def test_unknown_exception_returns_empty_dict() -> None:
    """An exception outside ``BUILTIN_MAP`` returns ``{}`` (yielded to Layer-C)."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    class _CustomDomainError(Exception):
        """User-defined exception not in BUILTIN_MAP."""

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(_CustomDomainError("novel")),
        span=object(),
        phase="exception",
    )

    assert payload == {}


# ── MRO inheritance walk ─────────────────────────────────────────────


def test_subclass_inherits_parent_classification() -> None:
    """A subclass of a mapped exception MUST inherit the parent's outcome."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        ExceptionBuiltinClassifier,
    )

    class _DomainTimeoutError(TimeoutError):
        """Custom timeout subclass — should fall back to TimeoutError's mapping."""

    producer = ExceptionBuiltinClassifier()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(_DomainTimeoutError()),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "timeout"
    assert payload["edge_case_id"] == "Timeout"
    assert payload["exception_class"] == "_DomainTimeoutError"


# ── BUILTIN_MAP surface ──────────────────────────────────────────────


def test_builtin_map_has_at_least_60_entries() -> None:
    """``BUILTIN_MAP`` MUST cover ~60 stdlib exception types (ADR-0165.1 §7.5.2)."""
    from lca.plugins.observability.spine.classifiers.exception_builtin import (
        BUILTIN_MAP,
    )

    assert len(BUILTIN_MAP) >= 60
    # Every value is a 2-tuple of non-empty strings.
    for exc_type, mapping in BUILTIN_MAP.items():
        assert isinstance(exc_type, type) and issubclass(exc_type, BaseException)
        assert isinstance(mapping, tuple) and len(mapping) == 2
        outcome, edge_case_id = mapping
        assert isinstance(outcome, str) and outcome
        assert isinstance(edge_case_id, str) and edge_case_id


# ── plugin manifest shape ────────────────────────────────────────────


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import classifiers

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(classifiers.exception_builtin, "setup")

    definition = definition_from_plugin(classifiers.exception_builtin.setup, module=__name__)
    assert definition.id == "spine.classifier.exception.builtin"
    assert definition.spec.layer == "L0"
    assert definition.provided_capability_keys == ("field_producer.exception.builtin",)


def test_module_export_surface() -> None:
    """The module exposes ``ExceptionBuiltinClassifier`` and ``BUILTIN_MAP``."""
    import lca.plugins.observability.spine.classifiers.exception_builtin as mod

    assert hasattr(mod, "ExceptionBuiltinClassifier")
    assert hasattr(mod, "BUILTIN_MAP")
    assert "ExceptionBuiltinClassifier" in mod.__all__
    assert "BUILTIN_MAP" in mod.__all__
    assert "setup" in mod.__all__
