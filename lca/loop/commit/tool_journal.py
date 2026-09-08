"""Tool journal catalog commit seam (ADR-0194 P1-10, P1-11, P1-12).

Prepared receipts from cognition (body tool lifecycle, brain llm_turn) commit
here via FactGateway. Phase tool spine EPs commit via ``publish_ep_bound``.
Unbound session → no-op (legacy journal path retires).
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.tool.journal_receipt import ToolJournalReceipt
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound


def _phase_tool_context() -> tuple[int, str]:
    from lca.infrastructure.observability.facade.run.ambit import current_run_ambit
    from lca.infrastructure.observability.facade.run.context import get_current_run_scope

    scope = get_current_run_scope()
    step = scope.step if scope is not None else 0
    run_id = str(scope.run_id) if scope is not None and scope.run_id else ""
    if not run_id:
        ambit = current_run_ambit()
        if ambit is not None and ambit.run_id:
            run_id = str(ambit.run_id)
    return step, run_id


def commit_tool_journal_receipt(
    receipt: ToolJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> AppendReceipt | None:
    """Commit one prepared tool catalog fact via FactGateway; no-op if unbound."""
    return append_catalog_bound(
        receipt.catalog_event,
        state=state,
        session=session,
        actor=receipt.actor,
    )


def commit_tool_phase_call_start(
    *,
    tool_name: str,
    invocation_id: str,
    arguments_summary: str = "",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``phase.tool.call.start`` spine fact via FactGateway."""
    step, run_id = _phase_tool_context()
    payload: dict[str, Any] = {
        "step": step,
        "run_id": run_id,
        "tool_name": tool_name,
        "invocation_id": invocation_id,
    }
    if arguments_summary:
        payload["arguments_summary"] = arguments_summary
    return publish_ep_bound(
        "phase.tool.call.start",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def commit_tool_phase_call_end(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: str,
    ok: bool | None = None,
    latency_ms: int | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``phase.tool.call.end`` spine fact via FactGateway."""
    step, run_id = _phase_tool_context()
    payload: dict[str, Any] = {
        "step": step,
        "run_id": run_id,
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "outcome": outcome,
    }
    if ok is not None:
        payload["ok"] = ok
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    return publish_ep_bound(
        "phase.tool.call.end",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def commit_tool_phase_denied(
    *,
    tool_name: str,
    reason: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``phase.tool.denied`` spine fact via FactGateway."""
    step, run_id = _phase_tool_context()
    return publish_ep_bound(
        "phase.tool.denied",
        {
            "step": step,
            "run_id": run_id,
            "tool_name": tool_name,
            "reason": reason,
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_tool_execute_start(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``body.tool.execute.start`` (invocation layer) via FactGateway."""
    return publish_ep_bound(
        "body.tool.execute.start",
        {
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_tool_execute_end(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
    outcome: str = "success",
    latency_ms: int | None = None,
    observation: Observation | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
    ok: bool | None = None,
) -> AppendReceipt | None:
    """Commit model-visible ``body.tool.execute.end`` surface (ADR-0201 single append).

    ``ok`` 与 ``outcome`` 一致:outcome="success" 对应 True,其他 False。
    显式接受 bool 是为了 fold binding / HOP 多源对账能拿到这个字段
    (spine.yaml 已声明 ``ok: bool``)。不传时从 outcome 派生。
    """
    from lca.infrastructure.session.emit.tool_surface_emit import append_tool_result_surface
    from lca.loop.fact_gateway import enrich_ep_payload

    del state
    if ok is None:
        ok = outcome == "success"
    enriched = enrich_ep_payload(
        "body.tool.execute.end",
        {
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
            "outcome": outcome,
            "ok": ok,
            **({"latency_ms": latency_ms} if latency_ms is not None else {}),
        },
    )
    receipt = append_tool_result_surface(
        tool_name=tool_name,
        invocation_id=invocation_id,
        attempt=attempt,
        outcome=outcome,
        observation=observation,
        latency_ms=latency_ms,
        session=session,
        actor=actor,
        enriched_fields=enriched,
    )
    return receipt


def commit_body_tool_decision_start(
    *,
    tool_name: str,
    invocation_id: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit decision-wrapper ``body.tool.execute.start`` via FactGateway."""
    return publish_ep_bound(
        "body.tool.execute.start",
        {
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": 1,
            "wrapper": "decision",
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_tool_decision_end(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit decision-wrapper ``body.tool.execute.end`` via FactGateway."""
    return publish_ep_bound(
        "body.tool.execute.end",
        {
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": 1,
            "wrapper": "decision",
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_tool_retry(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    reason: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``body.tool.retry`` spine fact via FactGateway."""
    return publish_ep_bound(
        "body.tool.retry",
        {
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
            "reason": reason,
            "outcome": "retrying",
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_sandbox_enter(
    *,
    invocation_id: str,
    tool_name: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``body.sandbox.enter`` spine fact via FactGateway."""
    return publish_ep_bound(
        "body.sandbox.enter",
        {
            "invocation_id": invocation_id,
            "tool_name": tool_name,
        },
        state=state,
        session=session,
        actor=actor,
    )


def commit_body_sandbox_exit(
    *,
    invocation_id: str,
    tool_name: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``body.sandbox.exit`` spine fact via FactGateway."""
    return publish_ep_bound(
        "body.sandbox.exit",
        {
            "invocation_id": invocation_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


# ── step.tool_call.record / step.tool_result.record narrow wrappers ──────────
# delete-when: cursor_record.CursorRecord.try_record_tool_call / try_record_tool_result
#   retired (ADR-0185 P5 owner; cursor second-track fully closed).
#   Until then, business-path callers route through these two functions and
#   never reach ``CursorRecord`` directly (C4 / I-FACT-1 single production entry).


def record_step_tool_call(
    *,
    tool_name: str,
    invocation_id: str,
    arguments: dict[str, Any] | None,
    arguments_summary: str = "",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``step.tool_call.record`` spine fact via FactGateway (single track).

    Replaces the legacy ``CursorRecord.try_record_tool_call`` second-track
    path on the business call sites (safe_executor / pipeline_safe_executor /
    tool_journal). Payload fields mirror what ``StdLoopCursor.record_tool_call``
    emits (excluding cursor-only fields ``incarnation`` / ``plan_ref`` /
    ``step_index`` / ``call_seq``, which are injected by the cursor itself
    on its own path and never reach the business path).
    """
    step, run_id = _phase_tool_context()
    payload: dict[str, Any] = {
        "step": step,
        "run_id": run_id,
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "arguments": arguments,
    }
    if arguments_summary:
        payload["arguments_summary"] = arguments_summary
    return publish_ep_bound(
        "step.tool_call.record",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def record_step_tool_result(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: Literal["ok", "failure", "timeout", "denied"],
    ok: bool,
    latency_ms: int = 0,
    stdout_head: str = "",
    stdout_chars_total: int = 0,
    stdout_truncated: bool = False,
    stderr: str = "",
    files_created: tuple[str, ...] = (),
    error: str | None = None,
    delta_summary: str = "",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "body",
) -> AppendReceipt | None:
    """Commit ``step.tool_result.record`` spine fact via FactGateway (single track).

    Replaces the legacy ``CursorRecord.try_record_tool_result`` second-track
    path. ``outcome`` / ``ok`` are both required and must agree — invariant
    from ``ToolResultRecord`` (contracts/observability/cursor/loop_cursor_payloads.py)
    and the fold binding ``FoldConsistencyError`` (binding_engine.apply_tool_result).
    """
    if outcome == "ok" and not ok:
        raise ValueError(
            f"tool_result contradiction: outcome='ok' requires ok=True, got ok=False "
            f"(tool={tool_name!r})"
        )
    if outcome in ("failure", "timeout", "denied") and ok:
        raise ValueError(
            f"tool_result contradiction: outcome={outcome!r} requires ok=False, "
            f"got ok=True (tool={tool_name!r})"
        )
    step, run_id = _phase_tool_context()
    payload: dict[str, Any] = {
        "step": step,
        "run_id": run_id,
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "outcome": outcome,
        "ok": ok,
        "latency_ms": latency_ms,
        "stdout_chars_total": stdout_chars_total,
        "stdout_truncated": stdout_truncated,
    }
    if stdout_head:
        payload["stdout_head"] = stdout_head
    if stderr:
        payload["stderr"] = stderr
    if files_created:
        payload["files_created"] = list(files_created)
    if error is not None:
        payload["error"] = error
    if delta_summary:
        payload["delta_summary"] = delta_summary
    return publish_ep_bound(
        "step.tool_result.record",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "commit_body_sandbox_enter",
    "commit_body_sandbox_exit",
    "commit_body_tool_decision_end",
    "commit_body_tool_decision_start",
    "commit_body_tool_execute_end",
    "commit_body_tool_execute_start",
    "commit_body_tool_retry",
    "commit_tool_journal_receipt",
    "commit_tool_phase_call_end",
    "commit_tool_phase_call_start",
    "commit_tool_phase_denied",
    "record_step_tool_call",
    "record_step_tool_result",
]
