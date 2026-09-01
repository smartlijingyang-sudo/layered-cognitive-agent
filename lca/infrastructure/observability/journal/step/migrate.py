"""journal.jsonl → journal.json (step-tree) 一次性迁移(ADR-0164 Phase 6)。

输入: traces/runs/<run_id>/journal.jsonl(老 v2 envelope 流式)
输出: traces/runs/<run_id>/journal.json(step-tree)+ journal.narrative.md

启发式分组(推断,标 ``migration_inferred: True``):

    1. ``AgentRunStarted`` / ``TeamRunStarted`` → 新 JournalMetadata.objective
    2. ``AgentRunFinished`` / ``TeamRunFinished`` → 新 metadata.outcome
    3. ``LlmCallStarted/Completed`` → step.thinking
    4. ``ReasoningDelta`` / ``StepTextDelta`` → step.spans
    5. ``ToolStarted/Invoked/ToolDenied`` → step.tool_call / tool_result
    6. ``ToolRetryProgress`` → step.spans
    7. ``SandboxOutputDelta`` → step.spans
    8. ``ContextManifested`` → step.context_before
    9. ``StepCompleted`` → close_step (outcome)
   10. ``DecisionMade`` → 合并到 thinking.decision

启发式 step 边界: 每次 ``ToolInvoked`` / ``LlmCallCompleted`` / ``AgentRunFinished``
算作一个 step 闭合。 ``scope.step`` 字段是主键 (Brain 内部递增)。

不解析 evidence / arguments_ref / output_ref(老事件里 EvidenceRef 引向
evidence/<sha>.json,迁移阶段读完整文件, 嵌入 step 字段)。

失败策略: 遇到 schema != "lca.journal/2" → 跳过 + 警告。 遇到无法分类
事件 → 放进最近的 step.spans, 不报错。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from lca.contracts.models.observability import (
    AttachmentRef,
    JournalDocument,
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    SpanRecord,
    StepContext,
    StepOutcome,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.step.projector import (
    StepGroupedProjector,
)

# ── 事件→原语 helpers ──


def _record_data(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("data") or {}


def _record_type(record: dict[str, Any]) -> str:
    descriptor = record.get("descriptor") or {}
    return str(descriptor.get("type", ""))


def _record_occurred_at(record: dict[str, Any]) -> float:
    ts = record.get("occurred_at")
    return float(ts) if isinstance(ts, (int, float)) else 0.0


def _record_step_index(record: dict[str, Any]) -> int:
    scope = record.get("scope") or {}
    return int(scope.get("step", 0) or 0)


def _record_agent_role(record: dict[str, Any]) -> str:
    scope = record.get("scope") or {}
    return str(scope.get("agent_role") or "")


def _record_run_id(record: dict[str, Any]) -> str:
    scope = record.get("scope") or {}
    return str(scope.get("run_id") or "")


def _record_trace_id(record: dict[str, Any]) -> str:
    scope = record.get("scope") or {}
    return str(scope.get("trace_id") or "")


# ── 迁移器 ──


class JournalMigrator:
    """从 v2 stream journal.jsonl 推断 step-tree + 写 journal.json。

    不读 evidence 文件(evidence/<sha>.json 由 reader 后续按需 fetch)。
    """

    def __init__(self, *, run_id: str, trace_id: str = "") -> None:
        self.run_id = run_id
        self.trace_id = trace_id
        self._objective: str = ""
        self._outcome: str = "in_progress"
        self._steps: dict[int, JournalStep] = {}
        self._step_counter: int = 0
        self._attachments: list[AttachmentRef] = []
        self._prev_summary: str | None = None
        self._first_ts: float | None = None
        self._last_ts: float | None = None

    def feed(self, record: dict[str, Any]) -> None:
        ts = _record_occurred_at(record)
        if self._first_ts is None:
            self._first_ts = ts
        self._last_ts = ts
        event_type = _record_type(record)
        data = _record_data(record)
        scope_step = _record_step_index(record)

        handler = _EVENT_HANDLERS.get(event_type)
        if handler is not None:
            handler(self, scope_step, event_type, data)
        else:
            # 未分类事件 → 放进最近 step 的 spans
            self._append_span(scope_step, event_type, data, ts)

    # ── handlers ──

    def _h_run_started(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "AgentRunStarted":
            self._objective = data.get("objective_preview") or data.get("objective") or ""

    def _h_run_finished(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        status = (data.get("status") or "completed").lower()
        # 老 status 映射 → 新 outcome
        mapping = {
            "completed": "completed",
            "running": "in_progress",
            "working": "in_progress",
            "failed": "failed",
            "fail": "failed",
            "canceled": "failed",
            "cancelled": "failed",
            "paused": "paused",
        }
        self._outcome = mapping.get(status, "completed")
        # 给最后 step 一个 reflect(如果有 output_text)
        output_text = data.get("output_text") or ""
        if output_text and self._steps:
            last_step_index = max(self._steps)
            last = self._steps[last_step_index]
            if last.reflect is None:
                self._steps[last_step_index] = asdict_replace(
                    last,
                    reflect=ReflectTrace(summary=output_text[:200]),
                )
        # 关闭所有 open step(用 final outcome 标记)
        for idx in list(self._steps.keys()):
            step = self._steps[idx]
            if step.outcome is None:
                # 跑完了 → 用 run final status 决定 outcome
                self._close_step(idx, outcome="fail" if self._outcome == "failed" else "ok")

    def _h_llm_started(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """LlmCallStarted: 开一个新 think step draft。"""
        if scope_step <= 0:
            return
        self._ensure_step(scope_step, "think")
        # 注意: 不立即写入 thinking,等 LlmCallCompleted 一起写

    def _h_llm_completed(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """LlmCallCompleted: 写 step.thinking。 不关闭 step(后续 tool 可能落到同一 scope.step)。"""
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "think")
        trace = ThinkingTrace(
            model=data.get("model") or "unknown",
            latency_ms=int(data.get("latency_ms") or 0),
            reasoning=(data.get("reasoning_preview") or "")[:1024],
            decision=(data.get("decision") or "respond"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            raw_response_preview=(data.get("response_preview") or "")[:1024],
        )
        self._steps[scope_step] = asdict_replace(step, thinking=trace)
        # 不调 _close_step: tool_started/invoked 接着落同一 scope.step

    def _h_tool_started(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "act")
        call = ToolCallRecord(
            invocation_id=str(data.get("invocation_id") or ""),
            name=str(data.get("tool_name") or "unknown"),
            arguments=data.get("arguments") or {},
            arguments_summary=_summarize_args(data.get("arguments") or {}),
        )
        self._steps[scope_step] = asdict_replace(step, tool_call=call)
        # 不调 _close_step: 同 scope.step 可能多次 tool

    def _h_tool_invoked(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "act")
        ok = bool(data.get("ok", True))
        result = ToolResult(
            ok=ok,
            latency_ms=int(data.get("latency_ms") or 0),
            stdout_head=(data.get("output_text") or "")[:500],
            stdout_chars_total=len(data.get("output_text") or ""),
            stdout_truncated=bool(data.get("output_truncated", False)),
            stderr=data.get("error") or "" if not ok else "",
            files_created=tuple(data.get("files") or ()),
            error=data.get("error") if not ok else None,
            delta_summary=_delta_summary_from_tool(data, ok),
        )
        self._steps[scope_step] = asdict_replace(step, tool_result=result)
        # 不调 _close_step: StepCompleted / AgentRunFinished 触发

    def _h_tool_denied(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "act")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind="tool_denied",
                started_at=self._last_ts or 0.0,
                summary={
                    "tool_name": data.get("tool_name"),
                    "reason": data.get("reason"),
                },
            ),
        )
        self._close_step(scope_step, outcome="fail")

    def _h_decision_made(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """DecisionMade 合并到 thinking.decision。"""
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "think")
        existing = step.thinking
        new_decision = data.get("action_type") or data.get("decision") or "respond"
        if existing is not None:
            self._steps[scope_step] = asdict_replace(
                step,
                thinking=ThinkingTrace(
                    model=existing.model,
                    latency_ms=existing.latency_ms,
                    reasoning=existing.reasoning,
                    decision=new_decision or existing.decision,
                    tool_call=existing.tool_call,
                    prompt_tokens=existing.prompt_tokens,
                    completion_tokens=existing.completion_tokens,
                    raw_response_preview=existing.raw_response_preview,
                ),
            )

    def _h_context_manifested(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """ContextManifested → step.context_before。"""
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "perceive")
        ctx = StepContext(
            objective=self._objective or "",
            prior_summary_chain=(self._prev_summary,) if self._prev_summary else (),
            extra={"item_kinds": data.get("item_kinds") or []},
        )
        self._steps[scope_step] = asdict_replace(step, context_before=ctx)
        self._close_step(scope_step, outcome="ok")

    def _h_step_completed(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """StepCompleted → 关闭对应 step(如果还没关)。"""
        if scope_step <= 0:
            return
        if scope_step in self._steps and self._steps[scope_step].outcome is None:
            status = data.get("status") or "completed"
            outcome = "fail" if status in ("failed", "fail", "error") else "ok"
            self._close_step(scope_step, outcome=outcome)

    def _h_reasoning_delta(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "think")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind="reasoning_delta",
                started_at=self._last_ts or 0.0,
                summary={"text_delta": data.get("text_delta", "")[:200]},
            ),
        )

    def _h_step_text_delta(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        if scope_step <= 0:
            return
        step = self._ensure_step(scope_step, "think")
        channel = data.get("channel", "decision")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind=f"step_text_delta:{channel}",
                started_at=self._last_ts or 0.0,
                summary={"text_delta": data.get("text_delta", "")[:200]},
            ),
        )

    def _h_tool_retry_progress(
        self, scope_step: int, event_type: str, data: dict[str, Any]
    ) -> None:
        """ToolRetryProgress → spans。"""
        step = self._ensure_step(scope_step, "act")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind="tool_retry_progress",
                started_at=self._last_ts or 0.0,
                summary={
                    "phase_id": data.get("phase_id"),
                    "attempt": data.get("attempt"),
                },
            ),
        )

    def _h_sandbox_output_delta(
        self, scope_step: int, event_type: str, data: dict[str, Any]
    ) -> None:
        step = self._ensure_step(scope_step, "act")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind="sandbox_output_delta",
                started_at=self._last_ts or 0.0,
                summary={
                    "invocation_id": data.get("invocation_id"),
                    "stream": data.get("stream"),
                    "text_delta": (data.get("text_delta") or "")[:200],
                },
            ),
        )

    def _h_attachment(self, scope_step: int, event_type: str, data: dict[str, Any]) -> None:
        """AttachmentStaging* → metadata.attachments。"""
        att = AttachmentRef(
            attachment_id=data.get("attachment_id", ""),
            name=data.get("name", ""),
            mime_type=data.get("mime_type", "application/octet-stream"),
            size_bytes=int(data.get("size_bytes") or 0),
            url=data.get("url", ""),
            direction="upload",
        )
        if att.name and att.name not in {a.name for a in self._attachments}:
            self._attachments.append(att)

    # ── helpers ──

    def _ensure_step(self, scope_step: int, phase: str) -> JournalStep:
        """确保 step 存在(scope_step 是主键), 不存在则创建新 draft。

        Phase 升级规则: think > act > perceive (主活动 = LLM/工具; perceive 是 prelude)。
        已有 step 时, 升级到更"主导"的 phase。
        """
        if scope_step in self._steps:
            existing = self._steps[scope_step]
            new_phase = _upgrade_phase(existing.phase, phase)
            if new_phase != existing.phase:
                self._steps[scope_step] = asdict_replace(existing, phase=new_phase)
            return self._steps[scope_step]
        self._step_counter = max(self._step_counter, scope_step)
        chain = (self._prev_summary,) if self._prev_summary else ()
        step = JournalStep(
            step_id=f"step_{scope_step}",
            step_index=scope_step,
            phase=phase,
            entered_at=self._last_ts or 0.0,
            context_before=StepContext(
                objective=self._objective or "",
                prior_summary_chain=chain,
            ),
        )
        self._steps[scope_step] = step
        return step

    def _close_step(self, scope_step: int, *, outcome: StepOutcome) -> None:
        if scope_step not in self._steps:
            return
        step = self._steps[scope_step]
        if step.outcome is not None:
            return
        # 写 reflect 摘要 (供下一步 prior_summary_chain)
        summary = ""
        if step.tool_result is not None and step.tool_result.delta_summary:
            summary = f"{'fail' if outcome == 'fail' else 'ok'} ({step.phase}): {step.tool_result.delta_summary}"
        elif step.reflect is not None and step.reflect.summary:
            summary = f"ok ({step.phase}): {step.reflect.summary}"
        else:
            summary = f"{'fail' if outcome == 'fail' else 'ok'} ({step.phase})"
        new_step = asdict_replace(
            step,
            exited_at=self._last_ts or 0.0,
            duration_ms=max(0, int(((self._last_ts or 0.0) - step.entered_at) * 1000)),
            reflect=ReflectTrace(summary=summary[:200]) if step.reflect is None else step.reflect,
            outcome=outcome,
            error=data_error_if_fail(step, outcome),
        )
        self._steps[scope_step] = new_step
        self._prev_summary = summary

    def _append_span(
        self, scope_step: int, event_type: str, data: dict[str, Any], ts: float
    ) -> None:
        step = self._ensure_step(scope_step, "think")
        self._append_span_to_step(
            step,
            SpanRecord(
                kind=event_type.lower(),
                started_at=ts,
                summary={"raw": str(data)[:200]},
            ),
        )

    def _append_span_to_step(self, step: JournalStep, span: SpanRecord) -> None:
        if step.step_index not in self._steps:
            return
        existing = self._steps[step.step_index].spans
        self._steps[step.step_index] = asdict_replace(
            self._steps[step.step_index],
            spans=(*existing, span),
        )

    # ── final ──

    def finalize(self) -> JournalDocument:
        """构造 JournalDocument 准备落盘。"""
        # 关所有未关的 step
        for idx in list(self._steps.keys()):
            step = self._steps[idx]
            if step.outcome is None:
                self._close_step(idx, outcome="skip")

        started_at = self._first_ts or 0.0
        closed_at = self._last_ts or started_at

        meta = JournalMetadata(
            agent_role=_infer_agent_role(self._steps),
            strategy_key="solo",
            plan_ref="",
            objective=self._objective or "(未提供)",
            attachments=tuple(self._attachments),
            outcome=self._outcome,
            started_at=started_at,
            closed_at=closed_at,
            total_steps=len(self._steps),
            extra={"migration_inferred": True},
        )

        doc = empty_document(
            run_id=self.run_id,
            trace_id=self.trace_id,
            metadata=meta,
            started_at=started_at,
        )
        # 按 step_index 顺序 append
        for idx in sorted(self._steps.keys()):
            doc = append_step(doc, self._steps[idx])
        return close_document(doc, outcome=self._outcome, closed_at=closed_at)


def asdict_replace(obj: Any, **changes: Any) -> Any:
    """不可变 replace helper(frozen dataclass)。"""
    from dataclasses import replace as _replace

    return _replace(obj, **changes)


_PHASE_PRIORITY = {"perceive": 0, "think": 2, "act": 1, "reflect": 1}


def _upgrade_phase(existing: str, incoming: str) -> str:
    """Phase 升级: 取较高优先级(主导活动)。"""
    if _PHASE_PRIORITY.get(incoming, 0) > _PHASE_PRIORITY.get(existing, 0):
        return incoming
    return existing


def data_error_if_fail(step: JournalStep, outcome: StepOutcome) -> str | None:
    if outcome != "fail":
        return None
    if step.tool_result is not None and step.tool_result.error:
        return step.tool_result.error
    return None


def _infer_agent_role(steps: dict[int, JournalStep]) -> str:
    """从 step.context_before 推断 agent_role。"""
    for step in steps.values():
        if step.context_before and step.context_before.extra.get("actor_role"):
            return str(step.context_before.extra["actor_role"])
    return ""


def _summarize_args(args: dict[str, Any], limit: int = 200) -> str:
    if not args:
        return ""
    keys = list(args.keys())[:5]
    head = ", ".join(f"{k}={repr(args[k])[:32]}" for k in keys)
    return head[:limit] + "…" if len(head) > limit else head


def _delta_summary_from_tool(data: dict[str, Any], ok: bool) -> str:
    if not ok:
        err = (data.get("error") or "unknown")[:120]
        return f"❌ {err}"
    files = data.get("files") or []
    if files:
        return f"✅ 写出 {len(files)} 个文件: {', '.join(str(f) for f in files[:3])}"
    out = (data.get("output_text") or "")[:80].replace("\n", "⏎")
    return f"✅ stdout[:80] = {out}" if out else "✅ ok"


# 事件类型 → handler 的 dispatch 表
_EVENT_HANDLERS: dict[str, Any] = {}


def _register_handlers() -> None:
    global _EVENT_HANDLERS
    if _EVENT_HANDLERS:
        return
    _EVENT_HANDLERS = {
        "AgentRunStarted": JournalMigrator._h_run_started,
        "TeamRunStarted": JournalMigrator._h_run_started,
        "AgentRunFinished": JournalMigrator._h_run_finished,
        "TeamRunFinished": JournalMigrator._h_run_finished,
        "LlmCallStarted": JournalMigrator._h_llm_started,
        "LlmCallCompleted": JournalMigrator._h_llm_completed,
        "ToolStarted": JournalMigrator._h_tool_started,
        "ToolInvoked": JournalMigrator._h_tool_invoked,
        "ToolDenied": JournalMigrator._h_tool_denied,
        "ToolLifecycleEnded": JournalMigrator._h_tool_invoked,
        "DecisionMade": JournalMigrator._h_decision_made,
        "ContextManifested": JournalMigrator._h_context_manifested,
        "StepCompleted": JournalMigrator._h_step_completed,
        "ReasoningDelta": JournalMigrator._h_reasoning_delta,
        "StepTextDelta": JournalMigrator._h_step_text_delta,
        "ToolRetryProgress": JournalMigrator._h_tool_retry_progress,
        "SandboxOutputDelta": JournalMigrator._h_sandbox_output_delta,
        "AttachmentStagingStarted": JournalMigrator._h_attachment,
        "AttachmentStagingCompleted": JournalMigrator._h_attachment,
    }


_register_handlers()


# ── CLI 入口 ──


def migrate_run(traces_root: Path, run_id: str) -> tuple[Path, Path]:
    """迁移一个 run: journal.jsonl → journal.json + journal.narrative.md。

    保留原 journal.jsonl(不删), 不影响 boot(boot 还会继续写 jsonl)。

    Returns:
        (journal_path, narrative_path) 写出的两个文件
    """
    jsonl_path = traces_root / "runs" / run_id / "journal.jsonl"
    if not jsonl_path.exists():
        raise FileNotFoundError(f"journal.jsonl not found: {jsonl_path}")
    migrator = JournalMigrator(run_id=run_id)
    last_trace_id = ""
    for record in load_journal_records(jsonl_path, strict=False):
        if record.get("schema") != "lca.journal/2":
            continue
        if not last_trace_id:
            last_trace_id = str(record.get("scope", {}).get("trace_id", ""))
        migrator.feed(record)
    migrator.trace_id = last_trace_id
    doc = migrator.finalize()

    journal_path = traces_root / "runs" / run_id / "journal.json"
    narrative_path = traces_root / "runs" / run_id / "journal.narrative.md"
    StepGroupedProjector(journal_path).write(doc)
    StepNarrativeWriter(narrative_path).write(doc)
    return journal_path, narrative_path


def iter_run_ids(traces_root: Path) -> Iterator[str]:
    """枚举所有有 journal.jsonl 的 run_id。"""
    runs_root = traces_root / "runs"
    if not runs_root.exists():
        return
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        if (run_dir / "journal.jsonl").exists():
            yield run_dir.name


__all__ = ["JournalMigrator", "iter_run_ids", "migrate_run"]
