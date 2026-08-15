"""InsightEngine —— post-commit subscriber，聚合事件，收尾时产出 insight（ADR-0055 N4）。

在 run 收尾（团队 ``TeamRunFinished`` / solo 根 ``AgentRunFinished``）把本
trace 的事件聚合成摘要，跑 ``insight_rules`` 注册表，把 ``RunInsight``
通过 ``store.append()`` 正常写入——与任何其他事件走同一路径。

不变量 N4：subscriber 是纯读者。产出的 RunInsight 走正常 append 路径，
不再通过 drain_followups 回写。

防自激：忽略入站 ``RunInsight``；每 trace 只在收尾触发一次。
装配顺序须 insight 先于 otel/console，保证洞察在 run span 关闭前注入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.models.observability.journal import (
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

if TYPE_CHECKING:
    from lca.layer0_infra.observability.journal.engine import RunStore


def _new_summary() -> dict[str, Any]:
    return {"tool_calls": [], "llm_calls": [], "runs": {}, "actions": {}}


class InsightEngine(JournalProjector):
    """Post-commit subscriber：聚合事件，收尾时产出 insight。

    须通过 ``bind_store`` 绑定 store 后才能产出 insight。
    未绑定时仍正常聚合（向后兼容），但不会产出 RunInsight。
    """

    def __init__(self) -> None:
        self._store: RunStore | None = None
        self._summaries: dict[str, dict[str, Any]] = {}

    def bind_store(self, store: RunStore) -> None:
        """绑定 store 引用——在 hub 构造后调用，解决循环依赖。"""
        self._store = store

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
            action = (
                f"{event.action_type}({event.tool_name})"
                if event.action_type == "use_tool" and event.tool_name
                else event.action_type
            )
            summary["actions"].setdefault(run_id, []).append(action)

    # ── 触发 ───────────────────────────────────────────
    @staticmethod
    def _is_finish(stamped: StampedEvent, event: JournalEvent) -> bool:
        if isinstance(event, TeamRunFinished):
            return True
        return isinstance(event, AgentRunFinished) and stamped.scope.parent_run_id is None

    def _emit_insights(self, stamped: StampedEvent) -> None:
        trace_id = stamped.scope.trace_id or "(unknown)"
        summary = self._summaries.pop(trace_id, None)
        if summary is None:
            return
        store = self._store
        if store is None:
            return
        for kind, message, detail in insight_rules.run_all_rules(summary):
            store.append(RunInsight(kind=kind, summary=message, detail=detail))


def create_insight_engine() -> InsightEngine:
    """工厂（注册表装配用）。"""
    return InsightEngine()
