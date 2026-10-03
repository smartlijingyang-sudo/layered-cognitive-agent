"""Contract pins for the stop-lift seam in :mod:`lca.loop.driver`.

``_stop_from_interpretation_output`` is the only place that turns raw
graph terminal payload ports into a real :class:`StopDecision` for the
non-pause path. Previously it had zero dedicated coverage: the pause
path (``_pause_from_interrupt`` / ``_paused_outcome_parts``) is pinned
by ``test_pause_from_interrupt.py``; this file pins the stop half.

Shape doubles are real contract classes (``StopDecision`` /
``StopPayload``) plus ``SimpleNamespace`` visit stand-ins — no
``MagicMock`` (repo lesson: ``runtime_checkable`` Protocol
``isinstance`` calls do not consult ``__getattr__``).
"""

from types import SimpleNamespace

import pytest

from lca.contracts.models.cognition.boundary import StopPayload
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.loop.driver import _stop_from_interpretation_output


def _respond_visit(text: str, node_id: str = "act.observe") -> SimpleNamespace:
    return SimpleNamespace(
        node_id=node_id,
        inputs={},
        outputs={"decision": SimpleNamespace(response_text=text)},
    )


@pytest.mark.parametrize("key", ("terminal_outcome", "stop_payload", "stop_decision", "stop"))
def test_explicit_stop_decision_returned_verbatim(key: str) -> None:
    """An explicit StopDecision on any terminal port is the decision."""
    expected = StopDecision(
        reason=StopReason.CONTINUE,
        final_output="done",
        status=TaskStatus.COMPLETED,
    )
    assert _stop_from_interpretation_output({key: expected}) is expected


def test_payload_with_no_reason_is_continue_completed() -> None:
    """Bare StopPayload presence is the terminal signal (no should_stop boolean)."""
    stop = _stop_from_interpretation_output(
        {"terminal_outcome": StopPayload()},
    )
    assert stop.reason is StopReason.CONTINUE
    assert stop.status is TaskStatus.COMPLETED
    assert stop.final_output is None


def test_payload_reason_budget_exceeded_is_failed() -> None:
    stop = _stop_from_interpretation_output(
        {"stop_payload": StopPayload(reason="budget_exceeded")},
    )
    assert stop.reason is StopReason.BUDGET_EXCEEDED
    assert stop.status is TaskStatus.FAILED


def test_payload_unknown_reason_maps_to_error() -> None:
    stop = _stop_from_interpretation_output(
        {"stop_decision": StopPayload(reason="no_such_reason")},
    )
    assert stop.reason is StopReason.ERROR
    assert stop.status is TaskStatus.FAILED


def test_payload_inline_ref_text_recovered() -> None:
    """Cutover quirk: literal answer text stashed in final_output_ref (has newline)."""
    stop = _stop_from_interpretation_output(
        {"stop_payload": StopPayload(final_output_ref="line one\nline two")},
    )
    assert stop.final_output == "line one\nline two"


def test_payload_journal_ref_resolved_from_newest_respond() -> None:
    """A journal pointer ref resolves against the newest respond decision in visits."""
    visits = (
        _respond_visit("old answer"),
        _respond_visit("new answer"),
    )
    stop = _stop_from_interpretation_output(
        {"stop_payload": StopPayload(final_output_ref="mem:abc123")},
        visits=visits,
    )
    assert stop.final_output == "new answer"


def test_visit_scan_returns_newest_stop_decision() -> None:
    """Ports empty: newest-first visit scan finds the innermost StopDecision."""
    older = StopDecision(reason=StopReason.BUDGET_EXCEEDED)
    newer = StopDecision(reason=StopReason.CONTINUE, final_output="late")
    visits = (
        SimpleNamespace(node_id="a", inputs={}, outputs={"stop_payload": older}),
        SimpleNamespace(node_id="b", inputs={}, outputs={"terminal_outcome": newer}),
    )
    assert _stop_from_interpretation_output({}, visits=visits) is newer


def test_nothing_present_falls_back_to_error() -> None:
    """No payload anywhere: explicit ERROR, not a silent CONTINUE."""
    stop = _stop_from_interpretation_output({})
    assert stop.reason is StopReason.ERROR


def test_nothing_present_with_irrelevant_visits_still_error() -> None:
    visits = (SimpleNamespace(node_id="x", inputs={}, outputs={"envelope": {}}),)
    stop = _stop_from_interpretation_output({}, visits=visits)
    assert stop.reason is StopReason.ERROR
