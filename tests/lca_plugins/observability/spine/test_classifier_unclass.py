"""Tests for ``spine.classifier.exception.unclass`` FieldProducer plugin.

Task 7.5 (Layer-C fallback): the producer catches every exception the
Layer-A ``ExceptionBuiltinClassifier`` could not map and emits the
``UnclassifiedError`` envelope. It tracks per-class occurrence counts
in an in-memory ``_seen_signatures`` index so a recurring exception
can graduate to ``recommended_action="add_to_BUILTIN_MAP"`` after the
third hit (operator signal to promote it into the Layer-A table).

The minimal contract pinned by this test:

- first occurrence of an unknown exception → ``first_seen=True``
  and ``recommended_action="track_more"``
- third occurrence of the same exception → ``first_seen=False``
  and ``recommended_action="add_to_BUILTIN_MAP"``
- ``outcome`` is always ``"unclassified"`` and
  ``edge_case_id="UnclassifiedError"``
- non-``"exception"`` phases return ``{}`` (no contribution)

State isolation across tests is achieved by creating a fresh producer
instance per test (``_fresh_producer`` fixture), since the counter
index lives on the instance.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.observability.spine.producer import FieldProducer

# ── helpers ──────────────────────────────────────────────────────────


def _ctx_with_exception(exc: BaseException) -> Any:
    """Build a minimal ``ctx`` carrying ``current_exception``."""

    class _Ctx:
        current_exception = exc

    return _Ctx()


class _NovelDomainError(Exception):
    """A user-defined exception outside the Layer-A BUILTIN_MAP."""


class _OtherDomainError(Exception):
    """Another unmapped exception type — used to confirm per-class isolation."""


@pytest.fixture
def fresh_producer() -> Any:
    """Yield a fresh ``UnclassClassifier`` so per-class counts do not bleed."""
    from lca.plugins.observability.spine.classifiers.exception_unclass import (
        UnclassClassifier,
    )

    return UnclassClassifier()


# ── protocol conformance ─────────────────────────────────────────────


def test_unclass_classifier_satisfies_field_producer_protocol(fresh_producer: Any) -> None:
    """``UnclassClassifier`` structurally implements ``FieldProducer``."""
    assert isinstance(fresh_producer, FieldProducer)


def test_unclass_classifier_metadata(fresh_producer: Any) -> None:
    """Producer exposes ``name`` / ``priority=99`` / ``enabled`` seam attrs."""
    assert fresh_producer.name == "spine.classifier.exception.unclass"
    assert fresh_producer.priority == 99
    assert fresh_producer.enabled is True


# ── first-seen semantics ─────────────────────────────────────────────


def test_first_occurrence_sets_first_seen_true(fresh_producer: Any) -> None:
    """First time we see an exception type, ``first_seen=True``."""
    payload = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(_NovelDomainError("boom")),
        span=object(),
        phase="exception",
    )

    assert payload["first_seen"] is True
    assert payload["recommended_action"] == "track_more"


def test_first_occurrence_records_exception_class_name(fresh_producer: Any) -> None:
    """``exception_class`` MUST carry the exception's ``__name__``."""
    payload = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(_NovelDomainError("boom")),
        span=object(),
        phase="exception",
    )

    assert payload["exception_class"] == "_NovelDomainError"


def test_first_occurrence_returns_unclassified_outcome(fresh_producer: Any) -> None:
    """``outcome`` and ``edge_case_id`` are the canonical UnclassifiedError keys."""
    payload = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=_ctx_with_exception(_NovelDomainError("boom")),
        span=object(),
        phase="exception",
    )

    assert payload["outcome"] == "unclassified"
    assert payload["edge_case_id"] == "UnclassifiedError"


# ── escalation after 3 occurrences ──────────────────────────────────


def test_three_occurrences_set_add_to_builtin_map(fresh_producer: Any) -> None:
    """Three hits on the same exception type escalate to add_to_BUILTIN_MAP."""
    exc = _NovelDomainError("boom")
    ctx = _ctx_with_exception(exc)

    # Hits 1 and 2 — still tracking more.
    payload_1 = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=ctx,
        span=object(),
        phase="exception",
    )
    payload_2 = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=ctx,
        span=object(),
        phase="exception",
    )
    assert payload_1["recommended_action"] == "track_more"
    assert payload_2["recommended_action"] == "track_more"
    assert payload_1["first_seen"] is True
    assert payload_2["first_seen"] is False

    # Hit 3 — promoted.
    payload_3 = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=ctx,
        span=object(),
        phase="exception",
    )
    assert payload_3["first_seen"] is False
    assert payload_3["recommended_action"] == "add_to_BUILTIN_MAP"
    assert payload_3["outcome"] == "unclassified"
    assert payload_3["edge_case_id"] == "UnclassifiedError"


def test_fourth_occurrence_remains_promoted(fresh_producer: Any) -> None:
    """Once escalated, subsequent hits still carry ``add_to_BUILTIN_MAP``."""
    exc = _NovelDomainError("boom")
    ctx = _ctx_with_exception(exc)

    for _ in range(4):
        payload = fresh_producer.produce(
            fn=lambda: None,
            args=(),
            kwargs={},
            ctx=ctx,
            span=object(),
            phase="exception",
        )

    assert payload["recommended_action"] == "add_to_BUILTIN_MAP"
    assert payload["first_seen"] is False


# ── per-class isolation ─────────────────────────────────────────────


def test_separate_exception_classes_have_independent_counts(fresh_producer: Any) -> None:
    """Counts are keyed by exception class — different types do not interfere."""
    novel_ctx = _ctx_with_exception(_NovelDomainError("a"))
    other_ctx = _ctx_with_exception(_OtherDomainError("b"))

    # Bump _NovelDomainError to escalation.
    for _ in range(3):
        fresh_producer.produce(
            fn=lambda: None,
            args=(),
            kwargs={},
            ctx=novel_ctx,
            span=object(),
            phase="exception",
        )

    # _OtherDomainError is still on its first hit.
    other_payload = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=other_ctx,
        span=object(),
        phase="exception",
    )
    assert other_payload["first_seen"] is True
    assert other_payload["recommended_action"] == "track_more"
    assert other_payload["exception_class"] == "_OtherDomainError"


# ── phase routing ────────────────────────────────────────────────────


def test_non_exception_phase_returns_empty_dict(fresh_producer: Any) -> None:
    """``produce(phase="pre"|"post")`` MUST return ``{}`` (no contribution)."""
    ctx = _ctx_with_exception(_NovelDomainError())

    assert (
        fresh_producer.produce(
            fn=lambda: None, args=(), kwargs={}, ctx=ctx, span=object(), phase="pre"
        )
        == {}
    )
    assert (
        fresh_producer.produce(
            fn=lambda: None, args=(), kwargs={}, ctx=ctx, span=object(), phase="post"
        )
        == {}
    )


def test_missing_exception_returns_empty_dict(fresh_producer: Any) -> None:
    """When ``ctx`` lacks ``current_exception``, the producer returns ``{}``."""
    payload = fresh_producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=object(),
        span=object(),
        phase="exception",
    )

    assert payload == {}


# ── plugin manifest shape ────────────────────────────────────────────


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import classifiers

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(classifiers.exception_unclass, "setup")

    definition = definition_from_plugin(classifiers.exception_unclass.setup, module=__name__)
    assert definition.id == "spine.classifier.exception.unclass"
    assert definition.spec.layer == "L0"
    assert definition.provided_capability_keys == ("field_producer.exception.unclass",)


def test_module_export_surface() -> None:
    """The module exposes ``UnclassClassifier`` and ``setup``."""
    import lca.plugins.observability.spine.classifiers.exception_unclass as mod

    assert hasattr(mod, "UnclassClassifier")
    assert hasattr(mod, "setup")
    assert "UnclassClassifier" in mod.__all__
    assert "setup" in mod.__all__
