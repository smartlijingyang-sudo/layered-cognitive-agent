"""StepGroupedReader —— JournalDocument 反序列化(ADR-0164 草案)。

配套 JournalDocumentWriter, 用于读回 ``journal.json``。 给 CLI
``lca-ops journal steps`` / doctor / debug 工具用。

不做的事:
    - 不解析 schema v1/v2(那些走 jsonl/projector.read_journal_records)。
    - 不缓存 / 不索引。 reader 是 stateless, 每次返回新 dataclass 实例。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import (
    JournalDocument,
    JournalMetadata,
)
from lca.contracts.models.observability.journal_step import (
    AttachmentRef,
    JournalStep,
    ReflectTrace,
    SegmentRecord,
    SpanRecord,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.models.observability.journal_totals import (
    PhaseRecord,
    Totals,
)


def _from_jsonable(obj: Any, cls: Any) -> Any:
    """递归把 dict → frozen dataclass。

    对每种已知类型显式匹配, 未知 → 透传。 tuple 字段 (如 spans) 必须
    显式还原, dataclasses 默认元组字段会变 list。
    """
    if isinstance(obj, list):
        # list 元素类型由外层构造器推断, 这里不做逐元素类型推断
        return [_from_jsonable(v, cls) for v in obj]
    if not isinstance(obj, dict):
        return obj
    # 按目标类分发
    if cls is JournalDocument:
        meta = _from_jsonable(obj["metadata"], JournalMetadata)
        steps_list = obj.get("steps", [])
        steps = tuple(_from_jsonable(s, JournalStep) for s in steps_list)
        totals = _from_jsonable(obj["totals"], Totals) if obj.get("totals") else None
        phases = tuple(_from_jsonable(p, PhaseRecord) for p in obj.get("phases", []))
        return cls(
            schema=obj["schema"],
            run_id=obj["run_id"],
            trace_id=obj["trace_id"],
            started_at=obj["started_at"],
            steps=steps,
            metadata=meta,
            closed_at=obj.get("closed_at"),
            totals=totals,
            phases=phases,
        )
    if cls is Totals:
        return cls(
            steps=obj["steps"],
            segments=obj["segments"],
            phases=obj["phases"],
        )
    if cls is SegmentRecord:
        return cls(
            segment_id=obj["segment_id"],
            kind=obj["kind"],
            phase_ref=obj.get("phase_ref"),
            started_at=obj.get("started_at", 0),
            ended_at=obj.get("ended_at"),
            outcome=obj.get("outcome"),
            extra=obj.get("extra", {}),
        )
    if cls is PhaseRecord:
        return cls(
            phase_id=obj["phase_id"],
            kind=obj["kind"],
            step_id=obj.get("step_id"),
            segment_id=obj.get("segment_id"),
            entered_at=obj.get("entered_at", 0),
            exited_at=obj.get("exited_at"),
            summary=obj.get("summary"),
            outcome=obj.get("outcome"),
            extra=obj.get("extra", {}),
        )
    if cls is JournalMetadata:
        attachments = tuple(_from_jsonable(a, AttachmentRef) for a in obj.get("attachments", []))
        return cls(
            agent_role=obj["agent_role"],
            strategy_key=obj["strategy_key"],
            plan_ref=obj["plan_ref"],
            objective=obj["objective"],
            attachments=attachments,
            outcome=obj.get("outcome", "in_progress"),
            started_at=obj.get("started_at", 0.0),
            closed_at=obj.get("closed_at"),
            total_steps=obj.get("total_steps", 0),
            extra=obj.get("extra", {}),
        )
    if cls is JournalStep:
        ctx = (
            _from_jsonable(obj.get("context_before"), StepContext)
            if obj.get("context_before")
            else None
        )
        thinking = (
            _from_jsonable(obj.get("thinking"), ThinkingTrace) if obj.get("thinking") else None
        )
        tool_call = (
            _from_jsonable(obj.get("tool_call"), ToolCallRecord) if obj.get("tool_call") else None
        )
        tool_result = (
            _from_jsonable(obj.get("tool_result"), ToolResult) if obj.get("tool_result") else None
        )
        reflect = _from_jsonable(obj.get("reflect"), ReflectTrace) if obj.get("reflect") else None
        spans = tuple(_from_jsonable(s, SpanRecord) for s in obj.get("spans", ()))
        return cls(
            step_id=obj["step_id"],
            step_index=obj["step_index"],
            phase=obj["phase"],
            entered_at=obj["entered_at"],
            exited_at=obj.get("exited_at"),
            duration_ms=obj.get("duration_ms"),
            parent_step_id=obj.get("parent_step_id"),
            subagent_role=obj.get("subagent_role"),
            context_before=ctx,
            thinking=thinking,
            tool_call=tool_call,
            tool_result=tool_result,
            reflect=reflect,
            spans=spans,
            outcome=obj.get("outcome"),
            error=obj.get("error"),
            segments=tuple(_from_jsonable(s, SegmentRecord) for s in obj.get("segments", [])),
        )
    if cls is StepContext:
        attachments = tuple(_from_jsonable(a, AttachmentRef) for a in obj.get("attachments", ()))
        return cls(
            objective=obj["objective"],
            attachments=attachments,
            prior_summary_chain=tuple(obj.get("prior_summary_chain", ())),
            cumulative_files=tuple(obj.get("cumulative_files", ())),
            extra=obj.get("extra", {}),
        )
    if cls is AttachmentRef:
        return cls(
            attachment_id=obj["attachment_id"],
            name=obj["name"],
            mime_type=obj["mime_type"],
            size_bytes=obj["size_bytes"],
            url=obj.get("url", ""),
            direction=obj.get("direction", "upload"),
        )
    if cls is ThinkingTrace:
        tool_call = (
            _from_jsonable(obj.get("tool_call"), ToolCallRecord) if obj.get("tool_call") else None
        )
        return cls(
            model=obj["model"],
            latency_ms=obj["latency_ms"],
            reasoning=obj.get("reasoning", ""),
            decision=obj.get("decision", ""),
            tool_call=tool_call,
            prompt_tokens=obj.get("prompt_tokens"),
            completion_tokens=obj.get("completion_tokens"),
            raw_response_preview=obj.get("raw_response_preview", ""),
        )
    if cls is ToolCallRecord:
        return cls(
            invocation_id=obj["invocation_id"],
            name=obj["name"],
            arguments=obj.get("arguments", {}),
            arguments_summary=obj.get("arguments_summary", ""),
        )
    if cls is ToolResult:
        return cls(
            ok=obj["ok"],
            latency_ms=obj["latency_ms"],
            stdout_head=obj.get("stdout_head", ""),
            stdout_chars_total=obj.get("stdout_chars_total", 0),
            stdout_truncated=obj.get("stdout_truncated", False),
            stderr=obj.get("stderr", ""),
            files_created=tuple(obj.get("files_created", ())),
            error=obj.get("error"),
            delta_summary=obj.get("delta_summary", ""),
        )
    if cls is ReflectTrace:
        return cls(
            summary=obj["summary"],
            verdict=obj.get("verdict", ""),
            extra=obj.get("extra", {}),
        )
    if cls is SpanRecord:
        return cls(
            kind=obj["kind"],
            started_at=obj["started_at"],
            ended_at=obj.get("ended_at"),
            summary=obj.get("summary", {}),
        )
    return obj


class StepGroupedReader:
    """journal.json 读取器。 无状态。"""

    def __init__(self, output_path: str | Path) -> None:
        self._path = Path(output_path)

    def read(self) -> JournalDocument:
        """读 journal.json, 还原为 JournalDocument。"""
        return read_step_document(self._path)

    def exists(self) -> bool:
        return self._path.exists()


def read_step_document(path: str | Path) -> JournalDocument:
    """便捷函数 —— 直接读路径。接受 lca.journal/3 与 lca.journal/3.1。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"journal step file not found: {p}")
    text = p.read_text(encoding="utf-8")
    obj = json.loads(text)
    schema = obj.get("schema")
    if schema not in {"lca.journal/3", "lca.journal/3.1"}:
        raise ValueError(
            f"read_step_document: expected schema in "
            f"{{'lca.journal/3', 'lca.journal/3.1'}}, got {schema!r}"
        )
    return _from_jsonable(obj, JournalDocument)


__all__ = ["StepGroupedReader", "read_step_document"]
