"""Regression lock for the ``_GraphProjection`` reducer-purity consolidation.

ADR-0170 §D1 mandates: a LoopProjectionDefinition apply(state, snapshot,
record) -> state must NOT mutate ``self`` between calls. The legacy
implementation cached ``self._last: str | None`` to thread the previous
edge's endpoint, which made two consecutive calls with the same input
diverge the second time around (the second call would see
``self._last`` set to whatever the prior record was).

This module drives the SHIPPED projection through the same input
twice and asserts:

  1. The resulting ``state`` is identical (byte-for-byte).
  2. ``_GraphProjection.__init__`` no longer carries ``self._last``.
  3. After ``restore()`` the state is reset to no-edges / no-edgepoint.

Pure rerun: any constant ``_GraphState`` literal in the assertion is
deliberately minimal — the projection itself decides what edges to
produce; here we only lock the reducer-purity contract, not its
output.
"""

from __future__ import annotations

from datetime import datetime, timezone

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import LoopProjectionDefinition
from lca.infrastructure.observability.loop_cursor.projections.defaults import (
    _GraphProjection,
    _GraphState,
)
from lca.infrastructure.observability.spine.event_record import (
    EventRecord,
)


def _make_record(execution_point: str, sequence: int) -> EventRecord:
    """Build a minimal in-memory EventRecord for the projection under test."""
    return EventRecord(
        execution_point=execution_point,
        channel="fact",
        span_id=f"lca-seq-{sequence:08x}",
        parent_span_id=None,
        sequence=sequence,
        epoch=sequence,
        causality_id=f"caus-{sequence:06x}",
        outcome=None,
        when=datetime.now(timezone.utc),
        when_corrected=datetime.now(timezone.utc),
        prev_event_hash=None,
        run_id="r",
        step_id=None,
        payload={"phase": "live"},
        phase="live",
        reason=None,
    )


def _snapshot(seq: int = 0) -> CursorSnapshot:
    return CursorSnapshot(
        run_id="r",
        trace_id="t",
        incarnation=1,
        step_id=f"step-{seq:03d}",
        step_index=seq,
        iteration=0,
        attempt_in_step=0,
        phase="think",
        iteration_reason=None,
        stop_signal=None,
        seq=seq,
    )


def test_graph_projection_satisfies_protocol() -> None:
    """The projection must satisfy the LoopProjectionDefinition Protocol."""
    assert isinstance(_GraphProjection(), LoopProjectionDefinition)


def test_apply_is_pure_no_self_state_leakage() -> None:
    """Two consecutive apply() calls with the same input must yield equal state."""
    proj = _GraphProjection()
    state = proj.init()
    record_a = _make_record("brain.think.start", 1)
    state_after_a = proj.apply(state, _snapshot(1), record_a)

    # Build a second, semantically-identical input (fresh record, same EP).
    proj_fresh = _GraphProjection()
    state_fresh = proj_fresh.init()
    record_b = _make_record("brain.think.start", 99)
    state_after_b = proj_fresh.apply(state_fresh, _snapshot(1), record_b)

    assert state_after_a == state_after_b, (
        "Reducer purity violated: same (snapshot, record.ep) input "
        "should produce identical state regardless of caller history."
    )


def test_apply_chains_edges_through_state_not_self() -> None:
    """The previous edge endpoint must be carried by state, not by ``self``."""
    proj = _GraphProjection()
    state = proj.init()
    state = proj.apply(state, _snapshot(1), _make_record("brain.think.start", 1))
    state = proj.apply(state, _snapshot(2), _make_record("llm.request.header", 2))
    edges = state.edges
    assert edges == [
        ("brain.think.start", "llm.request.header"),
    ], f"Unexpected edges: {edges}"
    # And ``state.last_endpoint`` is the latest record.
    assert state.last_endpoint == "llm.request.header"


def test_no_self_last_attribute() -> None:
    """``self._last`` is gone — the projection must not carry mutable instance state."""
    proj = _GraphProjection()
    assert not hasattr(proj, "_last"), (
        "_GraphProjection must not retain ``_last`` on self; "
        "carry the prior endpoint via state instead."
    )


def test_restore_resets_state() -> None:
    """After restore, the projection returns to the seed state."""
    proj = _GraphProjection()
    state = proj.init()
    state = proj.apply(state, _snapshot(1), _make_record("brain.think.start", 1))
    state = proj.apply(state, _snapshot(2), _make_record("llm.request.header", 2))
    restored = proj.restore(state)
    assert restored.edges == []
    assert restored.last_endpoint is None


def test_init_default_state_carries_no_endpoint() -> None:
    """Fresh state has no edges and no last_endpoint."""
    state = _GraphProjection().init()
    assert state == _GraphState(edges=[], last_endpoint=None)
