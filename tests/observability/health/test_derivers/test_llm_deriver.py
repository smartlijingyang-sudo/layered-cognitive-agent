"""Contract tests for ``LlmDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       every tool_call in a turn has a matching ``role=tool`` (or
             ``role=user`` with tool payload) message in the NEXT
             ``llm.request.header``'s messages.
    degraded some (but not all) tool_calls match.
    failed   zero tool_calls match.
    unknown  no ``llm.*`` events.

The brief originally describes the algorithm against
``llm.call.end.outputs.llm_response.tool_calls``; the v1 producer
emits tool_calls inside the ``assistant`` role messages of
``llm.request.header``. The deriver therefore reads tool_call ids
from assistant messages and matches them against ``role=tool`` /
``role=user`` (with tool payload) messages in the *next*
``llm.request.header``. This implements the B-1 detection: tool
results that the model never sees (``tool_calls`` ids that never
appear as role=tool in any subsequent header) become ``failed``.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _llm_header(
    *,
    event_id: str,
    ts: str = "2026-09-16T02:50:14.348897+00:00",
    run_id: str = "run_x",
    messages: list[dict] | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point="llm.request.header",
        payload={"messages": messages if messages is not None else []},
    )


def test_llm_returns_ok_when_all_tool_calls_have_matching_tool_messages() -> None:
    """Two tool calls in turn 1, both appear as role=tool in turn 2."""
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events = [
        _llm_header(
            event_id="run_x:1",
            messages=[
                {"role": "assistant", "tool_calls": [
                    {"id": "toolu_a"},
                    {"id": "toolu_b"},
                ]},
            ],
        ),
        _llm_header(
            event_id="run_x:2",
            messages=[
                {"role": "tool", "tool_call_id": "toolu_a", "content": "ok"},
                {"role": "tool", "tool_call_id": "toolu_b", "content": "ok"},
            ],
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "llm"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "llm_tool_messages_complete"


def test_llm_returns_degraded_when_partial_match() -> None:
    """2 tool_calls, only 1 has a matching role=tool in the next header."""
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events = [
        _llm_header(
            event_id="run_x:1",
            messages=[
                {"role": "assistant", "tool_calls": [
                    {"id": "toolu_a"},
                    {"id": "toolu_b"},
                ]},
            ],
        ),
        _llm_header(
            event_id="run_x:2",
            messages=[
                {"role": "tool", "tool_call_id": "toolu_a", "content": "ok"},
                # toolu_b is missing -> orphan, B-1 root cause
            ],
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "degraded"
    assert conditions[0].reason == "llm_tool_messages_partial"


def test_llm_returns_failed_when_zero_match() -> None:
    """1 tool_call in turn 1, no matching role=tool in turn 2."""
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events = [
        _llm_header(
            event_id="run_x:1",
            messages=[
                {"role": "assistant", "tool_calls": [{"id": "toolu_orphan"}]},
            ],
        ),
        _llm_header(
            event_id="run_x:2",
            messages=[{"role": "user", "content": "ok"}],
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"
    assert conditions[0].reason == "llm_tool_messages_missing"


def test_llm_returns_unknown_when_no_llm_events() -> None:
    """No llm.* events -> unknown."""
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "llm"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "llm_no_events"
    assert conditions[0].evidence_refs == ()


def test_llm_handles_no_tool_calls_in_turn() -> None:
    """A header with only user/assistant (no tool_calls) is vacuously ok."""
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events = [
        _llm_header(
            event_id="run_x:1",
            messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "ok"


def test_llm_aggregates_across_multiple_turns() -> None:
    """Multiple turn pairs are evaluated together; worst status wins.

    Turn 1 (header 1 -> header 2): all match (ok).
    Turn 2 (header 2 -> header 3): zero match (failed).
    Worst status wins -> ``failed``.

    Three tool_calls total (toolu_a, toolu_b, toolu_c) and only
    ``toolu_a`` is matched, so two are missing — degraded (some match,
    not all). To exercise the ``failed`` aggregation path, the third
    tool_call must NOT have a matching tool message in any subsequent
    header, AND no other tool_call may have a match.
    """
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    deriver = LlmDeriver()
    events = [
        _llm_header(
            event_id="run_x:1",
            messages=[
                {"role": "assistant", "tool_calls": [{"id": "toolu_a"}]},
            ],
        ),
        _llm_header(
            event_id="run_x:2",
            messages=[
                {"role": "tool", "tool_call_id": "toolu_a", "content": "ok"},
                {"role": "assistant", "tool_calls": [{"id": "toolu_b"}]},
            ],
        ),
        _llm_header(
            event_id="run_x:3",
            messages=[
                {"role": "user", "content": "next question"},
                # toolu_b is missing -> degraded (some matched, some not)
            ],
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "degraded"