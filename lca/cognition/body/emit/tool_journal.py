"""Canonical ToolStarted / ToolInvoked / ToolDenied prepare + observability seam.

Per spec §9.1 + journal boundary guard, ``lca.cognition.body.safe_executor``
is the single canonical site for the three tool lifecycle facts. Cognition
prepares :class:`ToolJournalReceipt` DTOs and records cursor/diagnostic
observability; loop ``tool_journal_commit`` commits catalog + phase spine facts.

ADR-0101 PR-2:tool 事件回归事实账本。``arguments`` / ``output`` 经
``EvidenceStore.prepare()`` 落到 evidence/<sha256>.json,event 的
``arguments_ref`` / ``output_ref`` 字段写入 ``EvidenceRef``;消费方
(前端 lobehub UI)经由 ref + EvidenceStore.get() 重组完整
state(可验证完整性)。``arguments`` inline 路径保留但 v1 强制走
evidence 平面,inline 由后续 EvidencePolicy.should_inline() 决策启用。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import structlog

from lca.cognition.body.emit._args_summary import summarize_args
from lca.cognition.body.tools.tool_result_preview import tool_files
from lca.contracts.models.core.execution.decision import Observation, ToolCall  # noqa: F401
from lca.contracts.models.observability.diagnostic.diagnostic import DiagnosticCategory
from lca.contracts.models.observability.tool.journal_receipt import (
    ToolJournalReceipt,
    tool_denied_receipt,
    tool_invoked_receipt,
    tool_started_receipt,
)
from lca.contracts.observability.evidence.evidence import (
    EvidencePolicy,
    EvidenceRef,
    EvidenceStore,
)
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.infrastructure.session.commit.fact_committer import emit_diagnostic
from lca.infrastructure.tools.contract.project.project import project_tool_state

_log = structlog.get_logger(__name__)


def prepare_state_evidence(
    state: Mapping[str, Any],
    *,
    evidence_store: EvidenceStore | None,
    evidence_policy: EvidencePolicy | None,
    prepared_by: str = "tool_journal_emit",
) -> EvidenceRef | None:
    """If ``state`` 应走 evidence 平面(ADR-0101 §5.3),写并返回 ``EvidenceRef``。

    决策路径:
    1. evidence_store / policy 不可用 → ``None``(调用方走 inline)
    2. state 为空 → ``None``(空 inline)
    3. policy.should_inline(payload, classification) == True → ``None``
       (payload 内联,无 round-trip)
    4. policy.should_inline(...) == False → ``prepare()`` 返回 ``EvidenceRef``

    默认 policy(DefaultEvidencePolicy.inline_threshold_bytes=64 KiB)对小
    public payload 直接 inline;restricted/confidential 永不 inline。
    调用方负责把 ref 写到对应 ToolStarted / ToolInvoked / ToolCallResolved
    的 ``arguments_ref`` / ``output_ref``。
    """
    if evidence_store is None or evidence_policy is None:
        return None
    if not state:
        return None
    try:
        payload = json.dumps(dict(state), ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return None
    classification = evidence_policy.classify(payload, media_type="application/json")
    if evidence_policy.should_inline(payload, classification=classification):
        return None
    retention = evidence_policy.retention(payload)
    receipt = evidence_store.prepare(
        payload,
        classification=classification,
        retention=retention,
        media_type="application/json",
        prepared_by=prepared_by,
    )
    return receipt.ref


def prepare_tool_started(
    tool: Tool,
    args: dict[str, Any],
    invocation_id: str,
    *,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
    idempotency_key: str = "",
) -> tuple[ToolJournalReceipt, EvidenceRef | None]:
    """Prepare ``ToolStarted`` catalog fact; commit via loop commit seam."""
    args_dict = dict(args)
    arguments_ref = prepare_state_evidence(
        args_dict,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    inline_args: dict[str, Any] = {} if arguments_ref is not None else args_dict
    receipt = tool_started_receipt(
        tool_name=tool.name,
        invocation_id=invocation_id,
        arguments=inline_args,
        arguments_ref=arguments_ref,
        idempotency_key=idempotency_key,
    )
    return receipt, arguments_ref


def record_tool_started_observability(
    tool: Tool,
    args: dict[str, Any],
    invocation_id: str,
    receipt: ToolJournalReceipt,
) -> None:
    """Record diagnostic + cursor evidence for a prepared ``ToolStarted``."""
    args_dict = dict(args)
    inline_args = dict(receipt.catalog_event.arguments)
    emit_diagnostic(
        category=DiagnosticCategory.TOOL.value,
        operation="tool.start",
        plugin=type(tool).__name__,
        attributes={
            "tool_name": tool.name,
            "invocation_id": invocation_id,
        },
    )
    from lca.loop.commit.tool_journal import (
        record_step_tool_call,
    )

    record_step_tool_call(
        tool_name=tool.name,
        invocation_id=invocation_id,
        arguments=inline_args,
        arguments_summary=summarize_args(args_dict),
    )


def emit_tool_started(
    tool: Tool,
    args: dict[str, Any],
    invocation_id: str,
    *,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
    idempotency_key: str = "",
) -> EvidenceRef | None:
    """Prepare ``ToolStarted`` and record observability; caller commits facts.

    ADR-0101 §5.3 inline 路径已启用:

    - ``evidence_policy.should_inline(payload, classification) == True``
      → ``arguments = dict(args)`` 内联,``arguments_ref = None``
      (小 + public payload 不走 evidence,无 round-trip)
    - 否则 → ``arguments = {}``,``arguments_ref = prepare_state_evidence(...)``
      (大 / restricted payload 走 evidence 平面)

    二选一(非空互斥, V2 / V4);evidence_store 不可用时强制 inline。
    返回 ref 供后续 ``emit_tool_invoked`` 携带同一 ref 关联。
    """
    receipt, arguments_ref = prepare_tool_started(
        tool,
        args,
        invocation_id,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
        idempotency_key=idempotency_key,
    )
    record_tool_started_observability(tool, args, invocation_id, receipt)
    return arguments_ref


def prepare_tool_denied(tool: Tool, reason: str) -> ToolJournalReceipt:
    """Prepare ``ToolDenied`` catalog fact; commit via loop commit seam."""
    return tool_denied_receipt(tool_name=tool.name, reason=reason)


def record_tool_denied_observability(tool: Tool, reason: str) -> None:
    """Record diagnostic + cursor evidence for a prepared ``ToolDenied``."""
    emit_diagnostic(
        category=DiagnosticCategory.TOOL.value,
        operation="tool.denied",
        plugin=type(tool).__name__,
        attributes={"tool_name": tool.name, "reason": reason},
    )
    from lca.loop.commit.tool_journal import (
        record_step_tool_result,
    )

    record_step_tool_result(
        tool_name=tool.name,
        invocation_id="",
        outcome="denied",
        ok=False,
        error=reason,
    )


def emit_tool_denied(tool: Tool, reason: str) -> ToolJournalReceipt:
    """Prepare ``ToolDenied`` and record observability; caller commits facts."""
    receipt = prepare_tool_denied(tool, reason)
    record_tool_denied_observability(tool, reason)
    return receipt


def prepare_tool_invoked(
    tool: Tool,
    args: dict[str, Any],
    obs: Observation,
    *,
    latency_ms: int,
    attempt: int,
    invocation_id: str,
    arguments_ref: EvidenceRef | None = None,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
) -> ToolJournalReceipt:
    """Prepare ``ToolInvoked`` catalog fact; commit via loop commit seam."""
    resolved_id = str((obs.extra or {}).get("invocation_id", "") or "") or invocation_id
    output_dict: dict[str, Any] = dict(obs.payload) if isinstance(obs.payload, dict) else {}
    output_ref = prepare_state_evidence(
        output_dict,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    if not obs.success:
        output_ref = None
    args_dict = dict(args)
    inline_args: dict[str, Any] = {} if arguments_ref is not None or not obs.success else args_dict
    inline_output_text: str | None = None
    if output_ref is None and obs.success:
        for key in ("output", "stdout", "content"):
            value = output_dict.get(key)
            if isinstance(value, str):
                inline_output_text = value
                break
    projected_state_dict: dict[str, Any] = {}
    try:
        projected_state_dict = project_tool_state(tool.name, args_dict, obs)
    except Exception:
        _log.debug("project_tool_state failed for %s", tool.name, exc_info=True)
    return tool_invoked_receipt(
        tool_name=tool.name,
        invocation_id=resolved_id,
        ok=obs.success,
        latency_ms=latency_ms,
        attempt=attempt,
        error="" if obs.success else (obs.error or ""),
        files=tool_files(obs),
        arguments=inline_args,
        arguments_ref=arguments_ref,
        output_ref=output_ref,
        output_text=inline_output_text,
        projected_state=projected_state_dict,
    )


def record_tool_invoked_observability(
    tool: Tool,
    obs: Observation,
    receipt: ToolJournalReceipt,
    *,
    latency_ms: int,
    attempt: int,
) -> None:
    """Record diagnostic + cursor evidence for a prepared ``ToolInvoked``."""
    committed = receipt.catalog_event
    resolved_id = committed.invocation_id
    inline_output_text = committed.output_text
    emit_diagnostic(
        category=DiagnosticCategory.TOOL.value,
        operation="tool.complete",
        plugin=type(tool).__name__,
        attributes={
            "tool_name": tool.name,
            "invocation_id": resolved_id,
            "attempt": attempt,
        },
        output={
            "ok": obs.success,
            "latency_ms": latency_ms,
            "error": "" if obs.success else (obs.error or ""),
        },
    )
    delta = _delta_summary_from_obs(
        obs,
        inline_output_text,
        committed.output_ref,
    )
    from lca.loop.commit.tool_journal import (
        record_step_tool_result,
    )

    record_step_tool_result(
        tool_name=tool.name,
        invocation_id=resolved_id,
        outcome="ok" if obs.success else "failure",
        ok=obs.success,
        latency_ms=latency_ms,
        stdout_head=(inline_output_text or "")[:2000],
        stderr="" if obs.success else (obs.error or ""),
        files_created=tuple(str(f.get("name") or "") for f in committed.files),
        error=obs.error or None,
        delta_summary=delta,
    )


def emit_tool_invoked(
    tool: Tool,
    args: dict[str, Any],
    obs: Observation,
    *,
    latency_ms: int,
    attempt: int,
    invocation_id: str,
    arguments_ref: EvidenceRef | None = None,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
) -> ToolJournalReceipt:
    """Prepare ``ToolInvoked`` and record observability; caller commits facts.

    ADR-0101 PR-2:``obs.payload`` 经 ``EvidenceStore.prepare()`` 走
    evidence 平面写到 ``output_ref``;``arguments_ref`` 由 ``emit_tool_started``
    返回并显式传入(便于 join ToolStarted↔ToolInvoked);失败时
    ``output_ref=None``,错误字符串承载在 ``error`` 字段。
    """
    receipt = prepare_tool_invoked(
        tool,
        args,
        obs,
        latency_ms=latency_ms,
        attempt=attempt,
        invocation_id=invocation_id,
        arguments_ref=arguments_ref,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    record_tool_invoked_observability(
        tool,
        obs,
        receipt,
        latency_ms=latency_ms,
        attempt=attempt,
    )
    return receipt


def _delta_summary_from_obs(
    obs: Observation,
    inline_output_text: str | None,
    output_ref: Any | None,
) -> str:
    """从 Observation 生成 step.tool_result.delta_summary(< 200 字符人话)。"""
    if not obs.success:
        err = (obs.error or "unknown")[:120]
        return f"❌ {type(err).__name__ if hasattr(err, '__class__') else 'err'}: {err}"
    files = tool_files(obs)
    if files:
        names = [str(f.get("name") or "") for f in files[:3]]
        return f"✅ 写出 {len(files)} 个文件: {', '.join(names)}"
    if inline_output_text:
        head = inline_output_text[:80].replace("\n", "⏎")
        return f"✅ stdout[:80] = {head}"
    if output_ref is not None:
        algo = (
            output_ref.get("algorithm", "?")
            if isinstance(output_ref, dict)
            else getattr(output_ref, "algorithm", "?")
        )
        return f"✅ 已落 evidence (ref={algo})"
    return "✅ ok"
