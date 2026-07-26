"""控制台可观测性实现 —— 把每个跨层调用输出为结构化 TraceSpan。"""

from __future__ import annotations

from contracts.observability import TraceSpan
from contracts.protocols import Observability


class ConsoleObservability(Observability):
    """默认可观测实现：结构化 TraceSpan 输出到控制台。"""

    def emit_span(self, span: TraceSpan) -> None:
        dur = None
        if span.ended_at:
            dur = int((span.ended_at - span.started_at).total_seconds() * 1000)
        print(f"  [TraceSpan] {span.name:<28} status={span.status:<5} dur_ms={dur} attrs={span.attributes}")
