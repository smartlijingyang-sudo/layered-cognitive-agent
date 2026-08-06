"""InsightEngine —— journal 聚合 + 规则触发的投影器（ADR-0037）。

在 run 收尾（团队 ``TeamRunFinished`` / solo 根 ``AgentRunFinished``）把本
trace 的事件聚合成摘要，跑 ``insight_rules`` 注册表，把每条发现 record 回
journal（``RunInsight``）——由此洞察自动流入一切投影（console Run Card、
OTel span event、jsonl 落盘），无需各投影器各自实现分析。

防自激：忽略入站 ``RunInsight``（自己产的不再触发）；每 trace 只在收尾
触发一次（收尾即 pop 摘要）。装配顺序须 insight 先于 otel/console，保证
洞察在 run span 关闭前注入、Run Card 渲染前就位。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    JournalEvent,
    LlmCallCompleted,
    RunInsight,
    StampedEvent,
    TeamRunFinished,
    ToolInvoked,
)
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.journal import insight_rules


def _new_summary() -> dict[str, Any]:
    return {"tool_calls": [], "llm_calls": [], "runs": {}, "actions": {}}


class InsightEngine(JournalProjector):
    """聚合 journal 事件，run 收尾触发洞察规则并回注 RunInsight。"""

    def __init__(self) -> None:
        self._summaries: dict[str, dict[str, Any]] = {}
        self._record: Any = None

    def bind_journal(self, record: Any) -> None:
        """延迟绑定 journal 写入端（hub 装配后注入 ``journal.record``）。"""
        self._record = record

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        event = stamped.event
        if isinstance(event, RunInsight):
            return  # 防自激
        self._aggregate(stamped, event)
        if self._is_finish(stamped, event):
            self._emit_insights(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self._summaries.clear()

    # ── 聚合 ───────────────────────────────────────────
    def _summary_of(self, stamped: StampedEvent) -> dict[str, Any]:
        trace_id = stamped.scope.trace_id or "(unknown)"
        return self._summaries.setdefault(trace_id, _new_summary())

    def _aggregate(self, stamped: StampedEvent, event: JournalEvent) -> None:
        summary = self._summary_of(stamped)
        run_id = stamped.scope.run_id
        if isinstance(event, ToolInvoked):
            summary["tool_calls"].append(
                {
                    "run_id": run_id,
                    "tool_name": event.tool_name,
                    "arguments": event.arguments_preview,
                }
            )
        elif isinstance(event, LlmCallCompleted):
            summary["llm_calls"].append(
                {
                    "run_id": run_id,
                    "model": event.model,
                    "latency_ms": event.latency_ms,
                    "prompt_tokens": event.prompt_tokens,
                    "completion_tokens": event.completion_tokens,
                }
            )
        elif isinstance(event, AgentRunStarted):
            summary["runs"].setdefault(run_id, {}).update(
                {"role": event.agent_role, "start_ts": stamped.ts}
            )
        elif isinstance(event, AgentRunFinished):
            run = summary["runs"].setdefault(run_id, {})
            run.update({"end_ts": stamped.ts, "steps": event.steps})
        elif isinstance(event, DecisionMade):
            summary["actions"].setdefault(run_id, []).append(event.action_type)

    # ── 触发 ───────────────────────────────────────────
    @staticmethod
    def _is_finish(stamped: StampedEvent, event: JournalEvent) -> bool:
        if isinstance(event, TeamRunFinished):
            return True
        # solo 根 run 的收尾（成员 run 有 parent_run_id，不触发）
        return isinstance(event, AgentRunFinished) and stamped.scope.parent_run_id is None

    def _emit_insights(self, stamped: StampedEvent) -> None:
        trace_id = stamped.scope.trace_id or "(unknown)"
        summary = self._summaries.pop(trace_id, None)
        if summary is None or self._record is None:
            return
        for kind, message, detail in insight_rules.run_all_rules(summary):
            self._record(RunInsight(kind=kind, summary=message, detail=detail))


def create_insight_engine() -> InsightEngine:
    """工厂（注册表装配用）。"""
    return InsightEngine()
