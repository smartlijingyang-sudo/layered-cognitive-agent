"""Tests for PR-6 orphan-event semantics.

ADR-0165.1 §19, design §4.3: orphan events carry ``phase="orphan"`` +
``reason`` (close enum), still flow to ``events.jsonl`` via the sink,
but are skipped by the step-tree projection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from lca.contracts.models.observability import JournalMetadata
from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.infrastructure.observability.spine.derivers.step_tree import (
    StepTreeDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.orphan import (
    CANCEL_PRE_BOOT,
    ORPHAN_REASONS,
    STOP_BEFORE_STEP,
    mark_orphan,
)
from lca.runtime.step_lifecycle import (
    StepLifecycleStore,
    reset_lifecycle_store,
    set_lifecycle_store,
)


def _meta() -> JournalMetadata:
    return JournalMetadata(
        agent_role="agt_orphan_test",
        strategy_key="solo",
        plan_ref="plan_orphan",
        objective="orphan phase PR-6 test",
    )


def _make_event(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "kernel.boot.start",
        "channel": "control",
        "span_id": "01HMABC",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": None,
        "payload": {"k": "v"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def _bound_store(tmp_path) -> tuple[StepGroupedBackend, StepTreeDeriver, object]:
    """Bind a fresh lifecycle store and build a deriver wrapping it."""
    store = StepLifecycleStore()
    store.bind_run(run_id="r-orphan", trace_id="t-orphan", metadata=_meta())
    token = set_lifecycle_store(store)
    backend = StepGroupedBackend(output_path=tmp_path / "journal.json", lifecycle_store=store)
    deriver = StepTreeDeriver(backend=backend)
    return backend, deriver, token


def test_orphan_phase_skipped_by_step_tree_deriver(tmp_path) -> None:
    """An orphan event must not reach the wrapped backend's write path."""
    _backend, deriver, token = _bound_store(tmp_path)
    try:
        rec = _make_event(phase="orphan", reason=CANCEL_PRE_BOOT)
        assert rec.phase == "orphan"
        assert rec.reason == CANCEL_PRE_BOOT

        with patch.object(StepGroupedBackend, "write", autospec=True) as spy:
            deriver.on_event(rec)

        spy.assert_not_called()
        # The flush path must not have materialised journal.json either,
        # because the orphan event never reached the backend.
        deriver.flush()
        assert not (tmp_path / "journal.json").exists()
    finally:
        reset_lifecycle_store(token)


def test_orphan_requires_reason() -> None:
    """``EventRecord(phase='orphan')`` without reason must raise."""
    with pytest.raises(ValueError, match="orphan events MUST carry reason"):
        _make_event(phase="orphan", reason=None)

    # Sanity: the record with a reason round-trips.
    rec = _make_event(phase="orphan", reason=STOP_BEFORE_STEP)
    assert rec.phase == "orphan"
    assert rec.reason == STOP_BEFORE_STEP


def test_mark_orphan_helper() -> None:
    """``mark_orphan`` returns a frozen-record copy tagged orphan."""
    live = _make_event()
    assert live.phase == "live"
    assert live.reason is None

    tagged = mark_orphan(live, CANCEL_PRE_BOOT)
    assert tagged.phase == "orphan"
    assert tagged.reason == CANCEL_PRE_BOOT
    # Original is untouched.
    assert live.phase == "live"
    assert live.reason is None
    # The full event payload is preserved.
    assert tagged.execution_point == live.execution_point
    assert tagged.span_id == live.span_id
    assert tagged.sequence == live.sequence
    assert tagged.causality_id == live.causality_id


def test_mark_orphan_rejects_already_orphan() -> None:
    """``mark_orphan`` is not idempotent on already-orphan records."""
    rec = _make_event(phase="orphan", reason=CANCEL_PRE_BOOT)
    with pytest.raises(ValueError, match="already phase='orphan'"):
        mark_orphan(rec, CANCEL_PRE_BOOT)


def test_orphan_reason_enum_is_closed() -> None:
    """The close enum exposes exactly the design §4.3 reasons."""
    assert (
        frozenset(
            {
                "cancel_pre_boot",
                "stop_before_step",
                "fail_before_step",
                "pending_tool_call",
                "panic",
            }
        )
        == ORPHAN_REASONS
    )
