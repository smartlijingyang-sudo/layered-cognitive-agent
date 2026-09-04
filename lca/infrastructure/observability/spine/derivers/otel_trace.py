# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine deriver；PR-8 shim 走 events/subscribers/spine_* 包装；
# 本模块保留至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.derivers" lca/ = 0 触发）。
#
# COMPAT(delete-when: ADR-0186 PR-3g otel fold 替代 callback deriver,
#        tracking: ADR-0186 PR-3g)
# otel_trace 累积 span 树;PR-3g 收口时改为从 SpineReader snapshot
# fold 出 OtelSpan 树(纯函数,events → root span),不再需要 on_event。

"""OTel-style trace deriver —— DSH ENTRY→AGENT→STEP→LLM|TOOL 投影（ADR-0167 D9）。

不抢全局 TracerProvider；产出内存中一棵 :class:`OtelSpan` 树，外部 sink
可选地把节点序列化为 OTLP JSON 或导出到 Langfuse。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord


@dataclass(frozen=True)
class OtelSpan:
    """OpenTelemetry-friendly span node。

    字段命名对齐 :genai: `gen_ai.client.operation.duration` 等约定；
    本 deriver 不写 OTel SDK，只构造可序列化节点。
    """

    name: str
    span_id: str
    parent_span_id: str | None
    kind: str  # "internal" | "client"
    start_seq: int
    end_seq: int | None
    attributes: dict[str, Any] = field(default_factory=dict)
    children: tuple[OtelSpan, ...] = ()

    def to_otel_attrs(self) -> dict[str, Any]:
        attrs: dict[str, Any] = dict(self.attributes)
        attrs["gen_ai.span.id"] = self.span_id
        if self.parent_span_id:
            attrs["gen_ai.parent.span.id"] = self.parent_span_id
        attrs["gen_ai.span.kind"] = self.kind
        return attrs


# EP → kind —— 单一真理表，避免重复 frozenset + if 链（ADR-0167 D13 B1）
EP_KINDS: dict[str, str] = {
    "kernel.run.start": "ENTRY",
    "kernel.run.stop": "ENTRY",
    "writable.step.start": "AGENT",
    "writable.step.end": "AGENT",
    "writable.segment.start": "STEP",
    "writable.segment.end": "STEP",
    "llm.call.start": "LLM",
    "llm.call.end": "LLM",
    "llm.stream.token": "LLM",
    "body.tool.execute.start": "TOOL",
    "body.tool.execute.end": "TOOL",
    "phase.tool.call.start": "TOOL",
    "phase.tool.call.end": "TOOL",
    "phase.tool.denied": "TOOL",
}

_CLIENT_KINDS = frozenset({"LLM", "TOOL"})


@dataclass(frozen=True)
class KindAttrSpec:
    """kind → 要从 payload 抽出的 Otel attribute 名。"""

    keys: tuple[str, ...] = ()


# 仅声明「需要什么键」；空 → 不抽
KIND_ATTRS: dict[str, KindAttrSpec] = {
    "LLM": KindAttrSpec(keys=("model",)),
    "TOOL": KindAttrSpec(keys=("tool_name", "invocation_id")),
}


@dataclass
class OtelTraceDeriver:
    """DSH ENTRY→AGENT→STEP→LLM|TOOL 树（ADR-0167 D9 / DSH trajectory 风格）。"""

    _spans_by_id: dict[str, OtelSpan] = field(default_factory=dict)
    _open_stack: list[OtelSpan] = field(default_factory=list)
    _root: OtelSpan | None = None

    def on_event(self, event: EventRecord) -> None:
        kind = EP_KINDS.get(event.execution_point)
        if kind is None:
            return
        if event.execution_point.endswith(".start"):
            self._open(event, kind)
        elif event.execution_point.endswith(".end"):
            self._close(event)

    def _open(self, event: EventRecord, kind: str) -> None:
        attrs = self._extract_attrs(kind, event)
        attrs["run_id"] = event.run_id
        attrs["step_id"] = event.step_id
        parent_id = self._open_stack[-1].span_id if self._open_stack else None
        span = OtelSpan(
            name=kind.lower(),
            span_id=event.span_id or f"lca-d-{event.sequence:08x}",
            parent_span_id=parent_id,
            kind="client" if kind in _CLIENT_KINDS else "internal",
            start_seq=event.sequence,
            end_seq=None,
            attributes=attrs,
        )
        self._spans_by_id[span.span_id] = span
        # First opened span is the trace root (DSH ENTRY→AGENT 顶层)
        if self._root is None and not self._open_stack:
            self._root = span
        self._open_stack.append(span)

    def _close(self, event: EventRecord) -> None:
        if not self._open_stack:
            return
        popped = self._open_stack.pop()
        closed = replace(
            popped,
            end_seq=event.sequence,
            attributes={
                **popped.attributes,
                "outcome": event.outcome or "unknown",
            },
        )
        self._spans_by_id[closed.span_id] = closed
        # Root pointer must follow the updated object even after replace().
        # Compare by identity since replace() returns a new object; the
        # root slot holds the same logical span and must be re-pointed.
        if self._root is not None and self._root.span_id == popped.span_id:
            self._root = closed
        if self._open_stack:
            self._open_stack[-1] = replace(
                self._open_stack[-1],
                children=(*self._open_stack[-1].children, closed),
            )

    def _extract_attrs(self, kind: str, event: EventRecord) -> dict[str, Any]:
        spec = KIND_ATTRS.get(kind)
        if spec is None:
            # 非 LLM / TOOL：内部 span，不带 domain attrs
            return {}
        return {key: event.payload.get(key, "") for key in spec.keys}

    @property
    def root(self) -> OtelSpan | None:
        return self._root

    def dump(self) -> list[dict[str, Any]]:
        """Export 全部 span 为扁平列表（按 start_seq 升序），供 OTLP / Langfuse 投影。"""
        return [
            {
                "name": s.name,
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "kind": s.kind,
                "start_seq": s.start_seq,
                "end_seq": s.end_seq,
                "attributes": s.to_otel_attrs(),
            }
            for s in sorted(
                self._spans_by_id.values(),
                key=lambda x: x.start_seq,
            )
        ]


__all__ = ["EP_KINDS", "OtelSpan", "OtelTraceDeriver"]
