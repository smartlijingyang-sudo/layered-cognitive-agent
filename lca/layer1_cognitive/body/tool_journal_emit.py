"""Canonical ToolStarted / ToolInvoked / ToolDenied emitters.

Per spec §9.1 + journal boundary guard, ``lca.layer1_cognitive.body.safe_executor``
is the single canonical emitter for the three tool lifecycle events.
Other consumers (e.g. ``pipeline_safe_executor``) must route through
this module so the journal sees exactly one emission site per event.

ADR-0065 §四 L5 / L8: ``plugin_state`` 超过 inline 阈值时,evidence 通过
``EvidenceStore.prepare()`` 落到 evidence/<sha256>.json,event 的
``state_ref`` 字段写入 ``EvidenceRef``;消费方(lcaJournal.ts / lobehub
UI)经由 ref + EvidenceStore.get() 重组完整 state(可验证完整性)。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from lca.contracts.models.core.decision import Observation, ToolCall  # noqa: F401
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.observability.evidence import (
    EvidencePolicy,
    EvidenceRef,
    EvidenceStore,
)
from lca.contracts.models.observability.journal import (
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.protocols.infra import Tool
from lca.layer0_infra.observability import record, record_runtime
from lca.layer1_cognitive.body.tool_result_preview import (
    tool_files,
    tool_plugin_state,
)


def _tool_output_preview(obs: Observation) -> str:
    """Compact success/error payload into a single-line preview.

    ADR-0065 §四: view-only 字段 —— journal_io emit 时从 disk 剥离,仅
    projector 视图层构造时使用。
    """
    if obs.success:
        return json.dumps(
            obs.payload,
            ensure_ascii=False,
            default=str,
        )
    return obs.error or ""


def _typed_started_state(state: Mapping[str, Any]) -> dict[str, object]:
    """Extract typed UI state fields from the legacy plugin_state dict.

    Maps known UI keys (per ``_WIRE_OVERLAY_KEYS``) to typed fields on
    ``ToolStarted`` / ``ToolInvoked`` so the disk v2 envelope carries
    structured facts instead of a free-shape ``plugin_state`` escape
    hatch (ADR-0065 §四)。
    """
    from lca.layer1_cognitive.body.tool_ui_state import _WIRE_OVERLAY_KEYS

    typed: dict[str, object] = {}
    for key in _WIRE_OVERLAY_KEYS:
        value = state.get(key)
        if not isinstance(value, str):
            continue
        if key in {"code", "command", "language", "skill_id", "description", "executionEnv"}:
            typed_field = "execution_env" if key == "executionEnv" else key
            typed[typed_field] = value
    return typed


def prepare_state_evidence(
    state: Mapping[str, Any],
    *,
    evidence_store: EvidenceStore | None,
    evidence_policy: EvidencePolicy | None,
    prepared_by: str = "tool_journal_emit",
) -> EvidenceRef | None:
    """If ``state`` 应走 evidence 平面(0065 L5),写并返回 ``EvidenceRef``。

    Returns ``None`` when:
    - evidence_store / evidence_policy 不可用(bound 未配 seam);
    - state 为空;
    - policy.should_inline() 返回 True(小 + public → 走 typed fields)。

    Returns ``EvidenceRef`` 当 state 走 evidence 平面;调用方负责把 ref
    写到对应 ToolStarted / ToolInvoked / ToolCallStreaming 的 ``state_ref``。
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
    args_preview: str,
    invocation_id: str,
    started_state: Mapping[str, Any],
    *,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
) -> None:
    """Emit ``ToolStarted`` from the canonical safe_executor module.

    typed state fields (code / command / language / skill_id /
    description / execution_env) extracted from ``started_state``;
    ``plugin_state`` kept for legacy UI / projector fallback;``state_ref``
    populated when ``evidence_store`` is provided and the state exceeds
    the inline threshold (ADR-0065 §四 L5)。
    """
    typed = _typed_started_state(started_state)
    state_ref = prepare_state_evidence(
        started_state,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.start",
        plugin=type(tool).__name__,
        attributes={
            "tool_name": tool.name,
            "invocation_id": invocation_id,
            "arguments_preview": args_preview,
        },
    )
    record(
        ToolStarted(
            tool_name=tool.name,
            arguments_preview=args_preview,
            invocation_id=invocation_id,
            plugin_state=dict(started_state),
            state_ref=state_ref,
            code=str(typed.get("code", "")),
            language=str(typed.get("language", "")),
            command=str(typed.get("command", "")),
            skill_id=str(typed.get("skill_id", "")),
            description=str(typed.get("description", "")),
            execution_env=str(typed.get("execution_env", "")),
        )
    )


def emit_tool_denied(tool: Tool, reason: str) -> None:
    """Emit ``ToolDenied`` from the canonical safe_executor module."""
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.denied",
        plugin=type(tool).__name__,
        attributes={"tool_name": tool.name, "reason": reason},
    )
    record(ToolDenied(tool_name=tool.name, reason=reason))


def emit_tool_invoked(
    tool: Tool,
    args: dict[str, Any],
    args_preview: str,
    obs: Observation,
    *,
    latency_ms: int,
    attempt: int,
    invocation_id: str,
    evidence_store: EvidenceStore | None = None,
    evidence_policy: EvidencePolicy | None = None,
) -> None:
    """Emit ``ToolInvoked`` from the canonical safe_executor module.

    typed state fields are extracted from the resolved plugin_state dict;
    ``output_text`` carries the full result text for structured recovery;
    ``state_ref`` is populated when ``evidence_store`` is provided and the
    state exceeds the inline threshold (ADR-0065 §四 L5)。
    """
    resolved_id = str((obs.extra or {}).get("invocation_id", "") or "") or invocation_id
    result_preview = _tool_output_preview(obs)
    plugin_state = tool_plugin_state(obs, tool_name=tool.name, args=args)
    typed = _typed_started_state(plugin_state)
    state_ref = prepare_state_evidence(
        plugin_state,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    record_runtime(
        DiagnosticCategory.TOOL,
        "tool.complete",
        plugin=type(tool).__name__,
        attributes={
            "tool_name": tool.name,
            "invocation_id": resolved_id,
            "arguments_preview": args_preview,
            "attempt": attempt,
        },
        output={
            "ok": obs.success,
            "latency_ms": latency_ms,
            "result_preview": result_preview,
            "error": "" if obs.success else (obs.error or ""),
        },
    )
    record(
        ToolInvoked(
            tool_name=tool.name,
            arguments_preview=args_preview,
            result_preview=result_preview,
            ok=obs.success,
            latency_ms=latency_ms,
            attempt=attempt,
            error="" if obs.success else (obs.error or ""),
            invocation_id=resolved_id,
            files=tool_files(obs),
            plugin_state=plugin_state,
            output_text="" if obs.success else (obs.error or ""),
            state_ref=state_ref,
            code=str(typed.get("code", "")),
            language=str(typed.get("language", "")),
            command=str(typed.get("command", "")),
            skill_id=str(typed.get("skill_id", "")),
            description=str(typed.get("description", "")),
            execution_env=str(typed.get("execution_env", "")),
        )
    )
