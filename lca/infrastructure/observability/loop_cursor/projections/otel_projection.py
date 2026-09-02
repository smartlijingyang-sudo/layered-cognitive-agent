"""OTel trace 出口 — LoopProjectionDefinition 实现(ADR-0172 D1)。

把 loop 事件映射到 OTel span。**若 opentelemetry-api 未安装,本出口降级为
no-op accumulator**:不在 import 时崩溃,apply 仍然累加最小 span 描述符到
内部 state;view 返回该列表;host 可在外部 flush 时落盘。

设计要点:
- try/except ImportError 在模块级进行;``_OTEL_AVAILABLE`` 与 ``_Tracer``
  是占位,在 SDK 缺席时为 None。
- reducer state 是 dict[str, Any](``{"spans": list[dict[str, Any]]}``),
  避免引入 ``opentelemetry`` 类型依赖 dataclass。
- ``apply`` 严格 reducer;不调用 tracer.start_as_current_span(那是
  view/flush 阶段的事,reducer 必须纯)。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.spine.event_record import EventRecord

# step.thinking.record / step.tool_call.record / llm.request.header
_EP_THINKING = "step.thinking.record"
_EP_TOOL_CALL = "step.tool_call.record"
_EP_TOOL_RESULT = "step.tool_result.record"
_EP_LLM_HEADER = "llm.request.header"

# OTel SDK 可选 import(ADR-0172 D5 / P1)
try:
    from opentelemetry import trace as _otel_trace  # type: ignore[import-not-found]

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - 由缺失依赖触发
    _otel_trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False


class OtelProjection:
    """OTel trace 出口 — emits one span per step。

    reducer 阶段(apply)只累加最小 span 描述符,确保 reducer 纯。
    真正的 SDK 导出发生在 view() —— host.flush_all 调用,profile 可挂
    trace exporter(OTLP / console / in-memory)。
    """

    key: str = "otel"
    version: int = 1

    def init(self) -> dict[str, Any]:
        """Seed state: spans 列表 + sdk_available flag。"""
        return {"spans": [], "sdk_available": _OTEL_AVAILABLE}

    def apply(
        self,
        state: dict[str, Any],
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> dict[str, Any]:
        """累加 span 描述符;不动 state,返回新 dict。"""
        spans = list(state.get("spans", []))
        sdk_available = state.get("sdk_available", _OTEL_AVAILABLE)

        if record.execution_point == _EP_LLM_HEADER:
            # 一次 LLM 请求 = 一个 span 起点
            spans.append(
                {
                    "name": "lca.llm.step",
                    "step_id": snapshot.step_id,
                    "sequence": record.sequence,
                    "attributes": _extract_attributes(record.payload),
                    "events": [],
                    "closed": False,
                }
            )
        elif record.execution_point == _EP_THINKING:
            spans.append(
                {
                    "name": "lca.step.thinking",
                    "step_id": snapshot.step_id,
                    "sequence": record.sequence,
                    "attributes": _extract_attributes(record.payload),
                    "events": [],
                    "closed": False,
                }
            )
        elif record.execution_point in (_EP_TOOL_CALL, _EP_TOOL_RESULT):
            spans.append(
                {
                    "name": f"lca.{record.execution_point}",
                    "step_id": snapshot.step_id,
                    "sequence": record.sequence,
                    "attributes": _extract_attributes(record.payload),
                    "events": [],
                    "closed": False,
                }
            )
        else:
            # 非 span EP:把 record 追加到最近 span 的 events
            if spans:
                spans[-1] = {
                    **spans[-1],
                    "events": [*spans[-1].get("events", []), _event_descriptor(record)],
                }

        return {"spans": spans, "sdk_available": sdk_available}

    def view(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """返回 spans 列表(供 host.flush_all 序列化)。"""
        return list(state.get("spans", []))

    def restore(self, state: dict[str, Any]) -> dict[str, Any]:
        """Checkpoint replay 入口;重置 spans(SDK 重新发射由上层决定)。"""
        return {"spans": [], "sdk_available": _OTEL_AVAILABLE}


def _extract_attributes(payload: object) -> dict[str, Any]:
    """从 payload 提取 attributes(仅保留基本类型)。"""
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
    return out


def _event_descriptor(record: EventRecord) -> dict[str, Any]:
    """构造 span event 描述符。"""
    return {
        "name": record.execution_point,
        "sequence": record.sequence,
        "attributes": _extract_attributes(record.payload),
    }


__all__ = ["OtelProjection"]


def otel_sdk_available() -> bool:
    """返回 opentelemetry-api 是否可用(测试 seam)。"""
    return _OTEL_AVAILABLE
