"""Tests for SpineContext (Task 1.3)."""

from __future__ import annotations

import pytest

from lca.infrastructure.observability.spine.context import (
    PhaseMachineViolation,
    SpineContext,
)


def test_set_run_and_step():
    SpineContext.set_run("r1")
    SpineContext.set_step("s1")
    assert SpineContext.get_run() == "r1"
    assert SpineContext.get_step() == "s1"


def test_sequence_monotonic():
    a = SpineContext.next_sequence()
    b = SpineContext.next_sequence()
    c = SpineContext.next_sequence()
    assert a < b < c
    assert a >= 1


def test_epoch_monotonic():
    a = SpineContext.next_epoch()
    b = SpineContext.next_epoch()
    assert a < b


def test_span_push_pop_match():
    span = SpineContext.push_span("brain.think.start")
    assert span.span_id
    assert span.parent_span_id is None
    assert SpineContext.current_span() is span
    back = SpineContext.pop_span("brain.think.start")
    assert back.span_id == span.span_id
    assert SpineContext.current_span() is None


def test_span_pop_mismatch_raises():
    SpineContext.push_span("brain.think.start")
    with pytest.raises(PhaseMachineViolation):
        SpineContext.pop_span("agent_loop.iteration.end")


def test_span_pop_empty_raises():
    with pytest.raises(PhaseMachineViolation):
        SpineContext.pop_span("kernel.run.start")


def test_nested_spans_parent_chain():
    root = SpineContext.push_span("kernel.run.start")
    inner = SpineContext.push_span("brain.think.start")
    assert inner.parent_span_id == root.span_id
    SpineContext.pop_span("brain.think.start")
    SpineContext.pop_span("kernel.run.start")


def test_hash_chain_replaces():
    SpineContext.chain_hash("abc")
    assert SpineContext.last_hash() == "abc"
    SpineContext.chain_hash("def")
    assert SpineContext.last_hash() == "def"
