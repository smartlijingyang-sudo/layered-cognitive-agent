"""Tests for the ``spine.spantree`` plugin (Task 7.6).

The plugin contributes the earliest ``FieldProducer`` in the merge
order (``priority=5``): it stamps ``span_id`` / ``parent_span_id``
from the span stack and mints ``sequence`` / ``epoch`` /
``prev_event_hash`` from the run-scoped counters held by
``SpineContext``.

The phase machine (I13) lives in ``SpineContext.push_span`` /
``pop_span``; this producer only reads it, so the tests here push a
span, call ``produce``, and pop it again — the pop is what asserts the
phase machine is untouched by the producer.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.observability.spine.context import SpanContext, SpineContext

REQUIRED_KEYS = (
    "span_id",
    "parent_span_id",
    "sequence",
    "epoch",
    "prev_event_hash",
)


@pytest.fixture(autouse=True)
def _isolated_spine_context() -> Any:
    """Give every test a clean run-scoped span stack and counters."""
    SpineContext.set_run("spantree-test")
    SpineContext._span_stack.set(())
    SpineContext._seq.set(0)
    SpineContext._epoch.set(0)
    SpineContext._span_counter.set(0)
    SpineContext._hash_chain.set(None)
    yield
    SpineContext._span_stack.set(())
    SpineContext._hash_chain.set(None)


def _produce(producer: Any, *, phase: str, span: Any = None) -> dict[str, Any]:
    """Call ``produce`` with the full keyword surface of the Protocol."""
    return producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=span,
        phase=phase,
    )


# ── protocol conformance / metadata ──────────────────────────────────


def test_spantree_producer_satisfies_field_producer_protocol() -> None:
    """``SpanTreeFieldProducer`` structurally implements ``FieldProducer``."""
    from lca.contracts.observability.spine.producer import FieldProducer
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    assert isinstance(SpanTreeFieldProducer(), FieldProducer)


def test_spantree_producer_metadata_runs_early() -> None:
    """Priority 5 keeps the spantree ahead of every other producer."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    assert producer.name == "spine.spantree"
    assert producer.priority == 5
    assert producer.enabled is True


# ── required keys ────────────────────────────────────────────────────


@pytest.mark.parametrize("phase", ["pre", "post"])
def test_produce_returns_all_required_keys(phase: str) -> None:
    """Both instrumented phases return the five spantree fields."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    span = SpineContext.push_span("brain.think.start")
    try:
        payload = _produce(producer, phase=phase, span=span)
    finally:
        SpineContext.pop_span("brain.think.start")

    for key in REQUIRED_KEYS:
        assert key in payload


def test_produce_reads_span_identity_from_pushed_span() -> None:
    """``span_id`` / ``parent_span_id`` mirror the pushed span."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    outer = SpineContext.push_span("runtime.turn.start")
    inner = SpineContext.push_span("brain.think.start")
    try:
        payload = _produce(producer, phase="pre", span=inner)
    finally:
        SpineContext.pop_span("brain.think.start")
        SpineContext.pop_span("runtime.turn.start")

    assert payload["span_id"] == inner.span_id
    assert payload["parent_span_id"] == outer.span_id


def test_produce_falls_back_to_current_span_when_span_arg_is_none() -> None:
    """Without a ``span`` argument the producer reads the stack top."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    span = SpineContext.push_span("brain.think.start")
    try:
        payload = _produce(producer, phase="pre", span=None)
    finally:
        SpineContext.pop_span("brain.think.start")

    assert payload["span_id"] == span.span_id
    assert payload["parent_span_id"] is None


def test_produce_without_any_span_returns_none_identity() -> None:
    """An empty span stack yields ``None`` identity, never a raise."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    payload = _produce(SpanTreeFieldProducer(), phase="pre", span=None)

    assert payload["span_id"] is None
    assert payload["parent_span_id"] is None


def test_produce_exception_phase_contributes_no_fields() -> None:
    """The exception envelope is owned by the classifier producers."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    assert _produce(SpanTreeFieldProducer(), phase="exception") == {}


# ── monotonic counters ───────────────────────────────────────────────


def test_sequence_and_epoch_are_monotonic_across_calls() -> None:
    """Every ``produce`` mints strictly increasing sequence + epoch."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    span = SpineContext.push_span("brain.think.start")
    try:
        payloads = [
            _produce(producer, phase="pre", span=span),
            _produce(producer, phase="post", span=span),
            _produce(producer, phase="pre", span=span),
        ]
    finally:
        SpineContext.pop_span("brain.think.start")

    sequences = [p["sequence"] for p in payloads]
    epochs = [p["epoch"] for p in payloads]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    assert epochs == sorted(epochs)
    assert len(set(epochs)) == len(epochs)


def test_prev_event_hash_tracks_the_context_hash_chain() -> None:
    """``prev_event_hash`` echoes ``SpineContext.last_hash()``."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    assert _produce(producer, phase="pre")["prev_event_hash"] is None

    SpineContext.chain_hash("sha256:deadbeef")
    assert _produce(producer, phase="pre")["prev_event_hash"] == "sha256:deadbeef"


def test_produce_does_not_mutate_the_span_stack() -> None:
    """The producer reads the phase machine; push/pop stay with the caller."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    producer = SpanTreeFieldProducer()
    span = SpineContext.push_span("brain.think.start")
    depth_before = SpineContext.span_stack_depth()

    _produce(producer, phase="pre", span=span)
    _produce(producer, phase="post", span=span)

    assert SpineContext.span_stack_depth() == depth_before
    assert SpineContext.current_span() is span
    # The caller's pop still matches — the phase machine is intact.
    assert SpineContext.pop_span("brain.think.start") is span


def test_produce_accepts_a_detached_span_context() -> None:
    """A span object passed explicitly wins over the stack top."""
    from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

    detached = SpanContext(
        execution_point="tool.execute.start",
        span_id="lca-span-000000ff",
        parent_span_id="lca-span-000000fe",
    )
    payload = _produce(SpanTreeFieldProducer(), phase="pre", span=detached)

    assert payload["span_id"] == "lca-span-000000ff"
    assert payload["parent_span_id"] == "lca-span-000000fe"


# ── plugin manifest shape ────────────────────────────────────────────


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_api import PluginKind
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import spantree

    assert hasattr(spantree, "setup")

    definition = definition_from_plugin(spantree.setup, module=__name__)
    assert definition.id == "spine.spantree"
    assert definition.spec.layer == "L0"
    assert definition.spec.kind == PluginKind.SEAM
    assert definition.provided_capability_keys == ("field_producer.spantree",)


def test_module_export_surface() -> None:
    """The module exposes ``SpanTreeFieldProducer`` and ``setup``."""
    import lca.plugins.observability.spine.spantree as mod

    assert "SpanTreeFieldProducer" in mod.__all__
    assert "setup" in mod.__all__
