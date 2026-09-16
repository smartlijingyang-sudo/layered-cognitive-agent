"""Contract tests for ``ToolDeriver`` (PR-1 / Task 1.3).

Covers the tool + sandbox sub-rule per spec §15 G-21. The tool
execution lifecycle is enter-sandbox → execute → exit-sandbox →
record-result; sandbox enter/exit mismatch is a tool-sub-condition
(not a peer condition), so this is the only deriver allowed to read
``body.sandbox.*`` EPs.

Status rules (spec §10.4):

    ok       every ``step.tool_call.record`` has a matching
             ``step.tool_result.record`` with ``ok=True`` AND every
             ``body.sandbox.enter`` has a matching ``body.sandbox.exit``
             AND no ``runtime.diagnostic`` (with ``operation`` starting
             ``tool.``) has ``output.ok == False``.
    degraded any tool_result has ``ok == False`` (tool returned an
             error but the call completed).
    failed   any tool_call has no matching tool_result OR any sandbox
             enter has no matching exit OR any tool diagnostic has
             ``output.ok == False`` (B-2 fix: read ``output.ok`` not
             ``payload.status``).
    unknown  no tool/sandbox events at all.

Multiple failing conditions may co-exist (a single run may have both
unmatched calls AND unmatched sandbox); the deriver emits one
condition per distinct cause with stable reason identifiers.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _tool_event(
    *,
    event_id: str,
    ts: str = "2026-09-16T02:50:14.070453+00:00",
    run_id: str = "run_x",
    execution_point: str = "step.tool_call.record",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {"invocation_id": "toolu_abc"},
    )


def test_tool_returns_ok_when_all_calls_matched_and_results_ok() -> None:
    """Happy path: every call has matching result with ok=True; sandbox balanced."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_a", "tool_name": "runCommand"},
        ),
        _tool_event(
            event_id="run_x:2",
            execution_point="body.sandbox.enter",
            payload={"invocation_id": "toolu_a"},
        ),
        _tool_event(
            event_id="run_x:3",
            execution_point="body.sandbox.exit",
            payload={"invocation_id": "toolu_a", "outcome": "success"},
        ),
        _tool_event(
            event_id="run_x:4",
            execution_point="step.tool_result.record",
            payload={"invocation_id": "toolu_a", "ok": True},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "tool"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "tool_calls_matched"


def test_tool_returns_degraded_when_tool_result_ok_false() -> None:
    """A ``step.tool_result.record`` with ``ok=False`` is degraded (call completed)."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_a"},
        ),
        _tool_event(
            event_id="run_x:2",
            execution_point="step.tool_result.record",
            payload={"invocation_id": "toolu_a", "ok": False},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "degraded"
    assert conditions[0].reason == "tool_result_failed"


def test_tool_returns_failed_when_tool_call_unmatched() -> None:
    """A ``step.tool_call.record`` with no matching ``step.tool_result.record`` is failed."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_orphan"},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert any(c.status == "failed" and c.reason == "tool_orphan_dropped" for c in conditions)


def test_tool_returns_failed_when_sandbox_enter_unmatched() -> None:
    """A ``body.sandbox.enter`` with no matching ``body.sandbox.exit`` is failed."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="body.sandbox.enter",
            payload={"invocation_id": "toolu_a"},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert any(
        c.status == "failed" and c.reason == "sandbox_enter_unmatched"
        for c in conditions
    )


def test_tool_returns_failed_when_diagnostic_output_ok_false() -> None:
    """A ``runtime.diagnostic`` with ``output.ok == False`` is failed (B-2 fix).

    Per spec §10.4 the deriver MUST read ``output.ok`` (not
    ``payload.status``) so the producer's ``status="failed"`` default
    does not poison successful operations.
    """
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="runtime.diagnostic",
            payload={
                "operation": "tool.complete",
                "tool_name": "runCommand",
                "status": "failed",  # B-2: ignore this field, read output.ok
                "output": {"ok": False, "error": "boom"},
            },
        ),
    ]
    conditions = deriver.evaluate(events)
    assert any(
        c.status == "failed" and c.reason == "tool_diagnostic_failed"
        for c in conditions
    )


def test_tool_returns_unknown_when_no_tool_events() -> None:
    """No tool/sandbox events -> unknown."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "tool"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "tool_no_events"


def test_tool_ignores_non_tool_diagnostic() -> None:
    """``runtime.diagnostic`` with operation not starting ``tool.`` is ignored.

    The deriver must NOT read LLM/lifecycle diagnostics. Only the
    tool-related subset counts toward tool health.
    """
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="runtime.diagnostic",
            payload={
                "operation": "llm.start",
                "output": {"ok": False},
            },
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "unknown"


def test_tool_failed_takes_priority_over_degraded() -> None:
    """When both unmatched-call and ok=False coexist, the worst status wins."""
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    deriver = ToolDeriver()
    events = [
        _tool_event(
            event_id="run_x:1",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_orphan"},  # unmatched -> failed
        ),
        _tool_event(
            event_id="run_x:2",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_a"},
        ),
        _tool_event(
            event_id="run_x:3",
            execution_point="step.tool_result.record",
            payload={"invocation_id": "toolu_a", "ok": False},  # degraded
        ),
    ]
    conditions = deriver.evaluate(events)
    statuses = {c.status for c in conditions}
    assert "failed" in statuses
    # degraded may also be reported as a separate condition; both can co-exist
    assert any(c.reason == "tool_orphan_dropped" for c in conditions)