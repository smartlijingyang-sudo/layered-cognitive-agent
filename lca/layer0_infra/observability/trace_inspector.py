"""面向 Coding Agent 的运行账本检查器。

检查器只读取已提交事件。它把大而完整的事件流投影为可解释的因果路径、失败
报告、性能候选和插件交互图，不维护增量缓存，也不会向事件账本回写分析结果。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    LlmCallCompleted,
    RuntimeObserved,
    StampedEvent,
    TeamRunFinished,
    ToolInvoked,
)

TraceFocus = Literal["all", "error", "latency", "tool", "plugin"]


@dataclass(frozen=True)
class TraceReport:
    """可序列化的 Agent 轨迹检查结果。"""

    trace_id: str
    event_count: int
    summary: str
    events: tuple[dict[str, Any], ...]
    causal_chain: tuple[int, ...] = ()
    bottlenecks: tuple[dict[str, Any], ...] = ()
    plugin_graph: str = ""


class TraceInspector:
    """从单一事件账本生成按需的机器可读诊断。"""

    def __init__(self, events: Sequence[StampedEvent]) -> None:
        self._events = tuple(events)
        self._by_seq = {event.seq: event for event in self._events}

    def inspect_trace(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        focus: TraceFocus = "all",
        depth: int = 24,
    ) -> TraceReport:
        events = self._select(trace_id=trace_id, run_id=run_id)
        selected = self._filter(events, focus)
        selected = selected[-max(depth, 1) :]
        chain = self._causal_chain(selected[-1]) if selected else ()
        resolved_trace = trace_id or (str(events[0].scope.trace_id) if events else "")
        return TraceReport(
            trace_id=resolved_trace,
            event_count=len(events),
            summary=self._summary(events, focus),
            events=tuple(self._render(event) for event in selected),
            causal_chain=chain,
            bottlenecks=tuple(self.find_optimization_candidates(events=events)),
            plugin_graph=self.plugin_interaction_graph(events=events),
        )

    def explain_failure(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        depth: int = 24,
    ) -> TraceReport:
        events = self._select(trace_id=trace_id, run_id=run_id)
        failure = next((event for event in events if self._is_failure(event)), None)
        if failure is None:
            return TraceReport(
                trace_id=trace_id or "",
                event_count=len(events),
                summary="未在所选事件中发现失败终态。",
                events=(),
            )
        chain = self._causal_chain(failure)
        related = [self._by_seq[seq] for seq in chain if seq in self._by_seq]
        window = [event for event in events if event.scope.run_id == failure.scope.run_id]
        selected = tuple((related + window)[-max(depth, 1) :])
        return TraceReport(
            trace_id=str(failure.scope.trace_id),
            event_count=len(events),
            summary=f"失败从 seq={failure.seq} 的 {failure.event_type} 开始；报告包含因果祖先和同 run 上下文。",
            events=tuple(self._render(event) for event in selected),
            causal_chain=chain,
            bottlenecks=tuple(self.find_optimization_candidates(events=events)),
            plugin_graph=self.plugin_interaction_graph(events=events),
        )

    def find_optimization_candidates(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for stamped in events if events is not None else self._events:
            event = stamped.event
            duration: int | None = None
            kind = ""
            name = ""
            if isinstance(event, LlmCallCompleted):
                duration, kind, name = event.latency_ms, "llm", event.model
            elif isinstance(event, ToolInvoked):
                duration, kind, name = event.latency_ms, "tool", event.tool_name
            elif isinstance(event, RuntimeObserved):
                duration, kind, name = event.duration_ms, event.kind, event.operation
            if duration is not None and duration > 0:
                candidates.append(
                    {"seq": stamped.seq, "kind": kind, "name": name, "duration_ms": duration}
                )
        return sorted(candidates, key=lambda item: int(item["duration_ms"]), reverse=True)[:limit]

    def export_minimal_reproduction(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """导出失败路径及其因果祖先，供脱机复现和差分。"""
        events = self._select(trace_id=trace_id, run_id=run_id)
        failure = next((event for event in events if self._is_failure(event)), None)
        if failure is None:
            return tuple(self._render(event) for event in events)
        seqs = set(self._causal_chain(failure)) | {failure.seq}
        return tuple(self._render(event) for event in events if event.seq in seqs)

    def plugin_interaction_graph(self, *, events: Iterable[StampedEvent] | None = None) -> str:
        edges: set[tuple[str, str, str]] = set()
        for stamped in events if events is not None else self._events:
            event = stamped.event
            if not isinstance(event, RuntimeObserved) or event.operation != "plugin.interaction":
                continue
            target = str(event.attributes.get("target_plugin", ""))
            if target:
                edges.add((event.source, target, event.outcome))
        lines = ["flowchart LR"]
        for source, target, outcome in sorted(edges):
            lines.append(f'    "{source}" -->|{outcome}| "{target}"')
        return "\n".join(lines) if len(lines) > 1 else "flowchart LR\n    Empty[无插件交互记录]"

    def _select(self, *, trace_id: str | None, run_id: str | None) -> tuple[StampedEvent, ...]:
        return tuple(
            event
            for event in self._events
            if (trace_id is None or str(event.scope.trace_id) == trace_id)
            and (run_id is None or str(event.scope.run_id) == run_id)
        )

    def _filter(
        self, events: Sequence[StampedEvent], focus: TraceFocus
    ) -> tuple[StampedEvent, ...]:
        if focus == "all":
            return tuple(events)
        if focus == "error":
            return tuple(event for event in events if self._is_failure(event))
        if focus == "latency":
            slow = {
                item["seq"] for item in self.find_optimization_candidates(events=events, limit=20)
            }
            return tuple(event for event in events if event.seq in slow)
        if focus == "tool":
            return tuple(event for event in events if isinstance(event.event, ToolInvoked))
        return tuple(event for event in events if isinstance(event.event, RuntimeObserved))

    def _causal_chain(self, event: StampedEvent) -> tuple[int, ...]:
        chain: list[int] = []
        current: StampedEvent | None = event
        visited: set[int] = set()
        while current is not None and current.seq not in visited:
            visited.add(current.seq)
            chain.append(current.seq)
            current = self._by_seq.get(current.parent_seq) if current.parent_seq else None
        return tuple(reversed(chain))

    @staticmethod
    def _is_failure(stamped: StampedEvent) -> bool:
        event = stamped.event
        return (
            (isinstance(event, RuntimeObserved) and str(event.outcome) == "error")
            or (isinstance(event, ToolInvoked) and not event.ok)
            or (
                isinstance(event, (AgentRunFinished, TeamRunFinished))
                and event.status in {"failed", "error", "cancelled"}
            )
        )

    @staticmethod
    def _summary(events: Sequence[StampedEvent], focus: TraceFocus) -> str:
        by_type: dict[str, int] = defaultdict(int)
        for event in events:
            by_type[event.event_type] += 1
        kinds = ", ".join(f"{name}×{count}" for name, count in sorted(by_type.items()))
        return f"focus={focus}；事件 {len(events)} 条；类型：{kinds or '无'}。"

    @staticmethod
    def _render(stamped: StampedEvent) -> dict[str, Any]:
        return {
            "seq": stamped.seq,
            "time": stamped.ts,
            "type": stamped.event_type,
            "scope": asdict(stamped.scope),
            "parent_seq": stamped.parent_seq,
            "data": stamped.data,
        }


__all__ = ["TraceFocus", "TraceInspector", "TraceReport"]
