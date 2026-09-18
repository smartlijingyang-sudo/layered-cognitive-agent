"""``ToolDeriver`` — observe tool calls, results, sandbox lifecycle, and
tool-related diagnostics (PR-1 / Task 1.3).

Covers the tool + sandbox sub-rule per spec §15 G-21: the tool
execution lifecycle is ``body.sandbox.enter`` → ``step.tool_call.record``
→ ``step.tool_result.record`` → ``body.sandbox.exit``. Sandbox
enter/exit mismatch is a tool-sub-condition, not a peer condition —
this is the only deriver allowed to read ``body.sandbox.*`` EPs.

Status rules (spec §10.4):

    ok       every ``step.tool_call.record`` has a matching
             ``step.tool_result.record`` with ``ok=True`` AND every
             ``body.sandbox.enter`` has a matching ``body.sandbox.exit``
             AND no ``runtime.diagnostic`` (with ``operation`` starting
             ``tool.``) has ``output.ok == False``.
    degraded any tool_result has ``ok == False``.
    failed   any tool_call is unmatched OR any sandbox enter is unmatched
             OR any tool diagnostic has ``output.ok == False``.

B-2 fix (per spec §10.4): the deriver MUST read ``output.ok`` (not
``payload.status``) on ``runtime.diagnostic`` events so the producer's
default ``status="failed"`` does not poison successful operations
(see spec §2 bullet B-2 and run_session_writer history-injection bug).
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    make_evidence_ref,
    parse_observed_at,
)

TOOL_CALL_EP: str = "step.tool_call.record"
TOOL_RESULT_EP: str = "step.tool_result.record"
SANDBOX_ENTER_EP: str = "body.sandbox.enter"
SANDBOX_EXIT_EP: str = "body.sandbox.exit"
DIAGNOSTIC_EP: str = "runtime.diagnostic"


class ToolDeriver:
    """Tool + sandbox health deriver.

    Emits one condition per distinct cause. ``unknown`` when no tool
    events exist at all. ``ok`` when all calls, results, and sandbox
    pairs balance cleanly. Multiple failed conditions may co-exist
    (unmatched calls AND unmatched sandbox entries); the fold
    aggregates them.
    """

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return conditions describing tool + sandbox health."""
        calls = filter_by_ep(events, TOOL_CALL_EP)
        results = filter_by_ep(events, TOOL_RESULT_EP)
        enters = filter_by_ep(events, SANDBOX_ENTER_EP)
        exits = filter_by_ep(events, SANDBOX_EXIT_EP)
        diagnostics = [e for e in filter_by_ep(events, DIAGNOSTIC_EP) if _is_tool_diagnostic(e)]

        has_any = any([calls, results, enters, exits, diagnostics])
        if not has_any:
            return [
                RunHealthCondition(
                    type="tool",
                    status="unknown",
                    reason="tool_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]

        conditions: list[RunHealthCondition] = []
        conditions.extend(_check_tool_results(results))
        conditions.extend(_check_tool_calls(calls, results))
        conditions.extend(_check_sandbox(enters, exits))
        conditions.extend(_check_diagnostics(diagnostics))

        if not conditions:
            # No problems found; emit a single ok condition.
            evidence_events = calls + results + enters + exits + diagnostics
            evidence = tuple(make_evidence_ref(e) for e in evidence_events)
            observed_at = max(parse_observed_at(e["ts"]) for e in evidence_events)
            return [
                RunHealthCondition(
                    type="tool",
                    status="ok",
                    reason="tool_calls_matched",
                    evidence_refs=evidence,
                    observed_at=observed_at,
                )
            ]
        return conditions


def _is_tool_diagnostic(event: SpineEvent) -> bool:
    """A diagnostic counts as tool-related if ``operation`` starts with ``tool.``."""
    op = event["payload"].get("operation")
    return isinstance(op, str) and op.startswith("tool.")


def _check_tool_results(results: list[SpineEvent]) -> list[RunHealthCondition]:
    """Emit degraded conditions for tool results with ``ok=False``."""
    out: list[RunHealthCondition] = []
    failed_results = [r for r in results if r["payload"].get("ok") is False]
    if not failed_results:
        return out
    evidence = tuple(make_evidence_ref(r) for r in failed_results)
    observed_at = max(parse_observed_at(r["ts"]) for r in failed_results)
    out.append(
        RunHealthCondition(
            type="tool",
            status="degraded",
            reason="tool_result_failed",
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    )
    return out


def _check_tool_calls(
    calls: list[SpineEvent],
    results: list[SpineEvent],
) -> list[RunHealthCondition]:
    """Emit failed conditions for tool_calls without a matching result.

    Calls marked ``status="pending_approval"`` are observed but not yet
    authorized (HITL pause); they have no result by design and must not be
    reported as orphaned executions.
    """
    out: list[RunHealthCondition] = []
    executed = [c for c in calls if c["payload"].get("status") != "pending_approval"]
    if not executed:
        return out
    result_ids = {r["payload"].get("invocation_id") for r in results}
    orphans = [c for c in executed if c["payload"].get("invocation_id") not in result_ids]
    if not orphans:
        return out
    evidence = tuple(make_evidence_ref(c) for c in orphans)
    observed_at = max(parse_observed_at(c["ts"]) for c in orphans)
    out.append(
        RunHealthCondition(
            type="tool",
            status="failed",
            reason="tool_orphan_dropped",
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    )
    return out


def _check_sandbox(
    enters: list[SpineEvent],
    exits: list[SpineEvent],
) -> list[RunHealthCondition]:
    """Emit failed conditions for sandbox enters without a matching exit."""
    out: list[RunHealthCondition] = []
    if not enters and not exits:
        return out
    exit_ids = {x["payload"].get("invocation_id") for x in exits}
    orphans = [e for e in enters if e["payload"].get("invocation_id") not in exit_ids]
    if not orphans:
        return out
    evidence = tuple(make_evidence_ref(e) for e in orphans)
    observed_at = max(parse_observed_at(e["ts"]) for e in orphans)
    out.append(
        RunHealthCondition(
            type="tool",
            status="failed",
            reason="sandbox_enter_unmatched",
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    )
    return out


def _check_diagnostics(
    diagnostics: list[SpineEvent],
) -> list[RunHealthCondition]:
    """Emit failed conditions for tool diagnostics with ``output.ok=False``."""
    out: list[RunHealthCondition] = []
    failed_diags = []
    for d in diagnostics:
        out_payload = d["payload"].get("output")
        if isinstance(out_payload, dict) and out_payload.get("ok") is False:
            failed_diags.append(d)
    if not failed_diags:
        return out
    evidence = tuple(make_evidence_ref(d) for d in failed_diags)
    observed_at = max(parse_observed_at(d["ts"]) for d in failed_diags)
    out.append(
        RunHealthCondition(
            type="tool",
            status="failed",
            reason="tool_diagnostic_failed",
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    )
    return out


__all__ = [
    "DIAGNOSTIC_EP",
    "SANDBOX_ENTER_EP",
    "SANDBOX_EXIT_EP",
    "TOOL_CALL_EP",
    "TOOL_RESULT_EP",
    "ToolDeriver",
]
