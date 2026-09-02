"""metrics 出口 — LoopProjectionDefinition 实现(ADR-0172 D1)。

按 step / phase / 工具调用 计数;高频事件流。
key = "metrics";version = 1。
state = MetricsState(step_count, tool_call_count, total_tokens)。
apply 纯 reducer;view 输出可序列化 dict(OpenMetrics JSON / Prometheus 文本)。

设计要点:
- 任何可选 SDK / 客户端都不引入(本 ADR 内 metrics 完全离线聚合)。
- 与 cursor 解耦:不读 cursor 内部字段,只读 snapshot。
- 不订阅 writable.iteration.close(L16 由 host 默认清单钉死)。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.spine.event_record import EventRecord

# step.thinking.record payload 字段(ADR-0168.1 §D4 ThinkingRecord)
_FIELD_TOKENS = "token_count"
# step.tool_call.record 与 step.tool_result.record EP 名
_EP_TOOL_CALL = "step.tool_call.record"
_EP_TOOL_RESULT = "step.tool_result.record"
_EP_THINKING = "step.thinking.record"


@dataclass
class MetricsState:
    """metrics 出口 reducer state。

    Attributes:
        step_count:        step.thinking.record 累计次数。
        tool_call_count:   step.tool_call.record 累计次数。
        total_tokens:      step.thinking.record payload.token_count 累计和(缺省按 0 累加)。
    """

    step_count: int = 0
    tool_call_count: int = 0
    total_tokens: int = 0


class MetricsProjection:
    """metrics 出口 — 计数器派生自 spine 事件。

    apply 严格 reducer:不修改入参 state,返回新 MetricsState。
    view 输出 dict,可由 host 在 flush_all 阶段序列化到 traces/runs/<id>/metrics.json。
    """

    key: str = "metrics"
    version: int = 1

    def init(self) -> MetricsState:
        """Seed reducer state。"""
        return MetricsState()

    def apply(
        self,
        state: MetricsState,
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> MetricsState:
        """纯 reducer;每个 EP 累加对应计数器。"""
        if record.execution_point == _EP_THINKING:
            tokens = _extract_token_count(record.payload)
            return MetricsState(
                step_count=state.step_count + 1,
                tool_call_count=state.tool_call_count,
                total_tokens=state.total_tokens + tokens,
            )
        if record.execution_point == _EP_TOOL_CALL:
            return MetricsState(
                step_count=state.step_count,
                tool_call_count=state.tool_call_count + 1,
                total_tokens=state.total_tokens,
            )
        if record.execution_point == _EP_TOOL_RESULT:
            # 结果也按一次工具调用增量(与 tool_call 配对计数)。
            return MetricsState(
                step_count=state.step_count,
                tool_call_count=state.tool_call_count + 1,
                total_tokens=state.total_tokens,
            )
        return state

    def view(self, state: MetricsState) -> dict[str, int]:
        """派生 side-effect target;host.flush_all 调用以触发落盘。"""
        return asdict(state)

    def restore(self, state: MetricsState) -> MetricsState:
        """Checkpoint replay 入口;重置为 seed(与 init 一致)。"""
        return MetricsState()


def _extract_token_count(payload: object) -> int:
    """从 payload 提取 token_count;非 dict 或缺字段视为 0。"""
    if not isinstance(payload, dict):
        return 0
    raw = payload.get(_FIELD_TOKENS)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    return 0


__all__ = ["MetricsProjection", "MetricsState"]
