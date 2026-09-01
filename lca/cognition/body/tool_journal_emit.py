"""Canonical ToolStarted / ToolInvoked / ToolDenied emitters.

Per spec §9.1 + journal boundary guard, ``lca.cognition.body.safe_executor``
is the single canonical emitter for the three tool lifecycle events.
All consumers (tool call sites, projectors) must route through this module
so the journal sees exactly one emission site per event.

ADR-0101 PR-2:tool 事件回归事实账本。``arguments`` / ``output`` 经
``EvidenceStore.prepare()`` 落到 evidence/<sha256>.json,event 的
``arguments_ref`` / ``output_ref`` 字段写入 ``EvidenceRef``;消费方
(lcaJournal.ts / lobehub UI)经由 ref + EvidenceStore.get() 重组完整
state(可验证完整性)。``arguments`` inline 路径保留但 v1 强制走
evidence 平面,inline 由后续 EvidencePolicy.should_inline() 决策启用。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.cognition.body.tool_result_preview import tool_files
from lca.contracts.models.core.decision import Observation, ToolCall  # noqa: F401
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.models.observability.journal import (
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.observability.evidence import (
    EvidencePolicy,
    EvidenceRef,
    EvidenceStore,
)
from lca.contracts.protocols.runtime.infra import Tool
from lca.infrastructure.observability import record, record_runtime
from lca.infrastructure.tools.contract.project import project_tool_state

_log = logging.getLogger(__name__)


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
    调用方负责把 ref 写到对应 ToolStarted / ToolInvoked / ToolCallStreaming
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


def emit_tool_started(
    tool: Tool,
    args: dict[str, Any],
    invocation_id: str,
    *,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
    idempotency_key: str = "",
) -> EvidenceRef | None:
    """Emit ``ToolStarted`` from the canonical safe_executor module.

    ADR-0101 §5.3 inline 路径已启用:

    - ``evidence_policy.should_inline(payload, classification) == True``
      → ``arguments = dict(args)`` 内联,``arguments_ref = None``
      (小 + public payload 不走 evidence,无 round-trip)
    - 否则 → ``arguments = {}``,``arguments_ref = prepare_state_evidence(...)``
      (大 / restricted payload 走 evidence 平面)

    二选一(非空互斥, V2 / V4);evidence_store 不可用时强制 inline。
    返回 ref 供后续 ``emit_tool_invoked`` 携带同一 ref 关联。
    """
    args_dict = dict(args)
    arguments_ref = prepare_state_evidence(
        args_dict,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    # V4:至少一个非空;evidence 不可用 → inline 退路
    inline_args: dict[str, Any] = {} if arguments_ref is not None else args_dict
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.start",
        plugin=type(tool).__name__,
        attributes={
            "tool_name": tool.name,
            "invocation_id": invocation_id,
        },
    )
    record(
        ToolStarted(
            tool_name=tool.name,
            invocation_id=invocation_id,
            arguments=inline_args,
            arguments_ref=arguments_ref,
            idempotency_key=idempotency_key,
        )
    )
    # ADR-0164 Phase 3 双写:写 step.tool_call(无 step_lifecycle 时 silent 跳过)
    try:
        from lca.runtime.step_emitter import bridge_tool_started

        # args 可能很大(arguments_summary 限 200 字符), 由 reader 自己读完整 arguments
        bridge_tool_started(
            tool_name=tool.name,
            invocation_id=invocation_id,
            arguments=args_dict,
            arguments_summary=_summarize_args(args_dict),
        )
    except ImportError:
        pass
    return arguments_ref


def _summarize_args(args: dict[str, Any], limit: int = 200) -> str:
    """生成 args 的一行人话摘要(进入 step.tool_call.arguments_summary)。"""
    if not args:
        return ""
    keys = list(args.keys())[:5]
    head = ", ".join(f"{k}={repr(args[k])[:32]}" for k in keys)
    if len(head) > limit:
        return head[:limit] + "…"
    return head


def emit_tool_denied(tool: Tool, reason: str) -> None:
    """Emit ``ToolDenied`` from the canonical safe_executor module."""
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.denied",
        plugin=type(tool).__name__,
        attributes={"tool_name": tool.name, "reason": reason},
    )
    record(ToolDenied(tool_name=tool.name, reason=reason))
    # ADR-0164 Phase 3 双写:ToolDenied 折叠为 step span
    try:
        from lca.runtime.step_emitter import bridge_tool_denied

        bridge_tool_denied(tool_name=tool.name, reason=reason)
    except ImportError:
        pass


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
) -> None:
    """Emit ``ToolInvoked`` from the canonical safe_executor module.

    ADR-0101 PR-2:``obs.payload`` 经 ``EvidenceStore.prepare()`` 走
    evidence 平面写到 ``output_ref``;``arguments_ref`` 由 ``emit_tool_started``
    返回并显式传入(便于 join ToolStarted↔ToolInvoked);失败时
    ``output_ref=None``,错误字符串承载在 ``error`` 字段。
    """
    resolved_id = str((obs.extra or {}).get("invocation_id", "") or "") or invocation_id
    output_dict: dict[str, Any] = dict(obs.payload) if isinstance(obs.payload, dict) else {}
    output_ref = prepare_state_evidence(
        output_dict,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    if not obs.success:
        output_ref = None
    # V4:inline arguments 非空退路(若 arguments_ref 已空);output_ref 已 ok 才非空
    args_dict = dict(args)
    inline_args: dict[str, Any] = {} if arguments_ref is not None or not obs.success else args_dict
    # Inline text result: take the common stdout keys from obs.payload when
    # the evidence store didn't materialize a ref. Empty string if absent
    # (frontend distinguishes empty-result from error via the `ok` flag).
    inline_output_text: str | None = None
    if output_ref is None and obs.success:
        for key in ("output", "stdout", "content"):
            value = output_dict.get(key)
            if isinstance(value, str):
                inline_output_text = value
                break
    # Renderer-facing state projection (SSE-only; stripped before jsonl).
    projected_state_dict: dict[str, Any] = {}
    try:
        projected_state_dict = project_tool_state(tool.name, args_dict, obs)
    except Exception:
        _log.debug("project_tool_state failed for %s", tool.name, exc_info=True)
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.complete",
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
    record(
        ToolInvoked(
            tool_name=tool.name,
            invocation_id=resolved_id,
            ok=obs.success,
            latency_ms=latency_ms,
            attempt=attempt,
            error="" if obs.success else (obs.error or ""),
            idempotency_key="",
            files=tool_files(obs),
            arguments=inline_args,
            arguments_ref=arguments_ref,
            output_ref=output_ref,
            output_text=inline_output_text,
            output_truncated=False,
            projected_state=projected_state_dict,
        )
    )
    # ADR-0164 Phase 3 双写:写 step.tool_result
    try:
        from lca.runtime.step_emitter import bridge_tool_invoked

        files = tool_files(obs)
        bridge_tool_invoked(
            tool_name=tool.name,
            invocation_id=resolved_id,
            ok=obs.success,
            latency_ms=latency_ms,
            error="" if obs.success else (obs.error or None),
            files_created=tuple(files),
            delta_summary=_delta_summary_from_obs(obs, inline_output_text, output_ref),
            stdout_head=(inline_output_text or "")[:500],
            stdout_chars_total=len(inline_output_text or ""),
            stdout_truncated=output_ref is not None,
            stderr=str(obs.error or "") if not obs.success else "",
        )
    except ImportError:
        pass


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
        return f"✅ 写出 {len(files)} 个文件: {', '.join(Path(f).name for f in files[:3])}"
    if inline_output_text:
        head = inline_output_text[:80].replace("\n", "⏎")
        return f"✅ stdout[:80] = {head}"
    if output_ref is not None:
        return f"✅ 已落 evidence (ref={getattr(output_ref, 'algorithm', '?')})"
    return "✅ ok"
