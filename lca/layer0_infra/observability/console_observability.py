"""控制台可观测性实现 —— 把每个跨层调用输出为结构化 TraceSpan。"""

from __future__ import annotations

import structlog

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability

_log = structlog.get_logger("lca.console")


class ConsoleObservability(Observability):
    """默认可观测实现：结构化 TraceSpan 输出到控制台。"""

    def emit_span(self, span: TraceSpan) -> None:
        dur = None
        if span.ended_at:
            dur = int((span.ended_at - span.started_at).total_seconds() * 1000)

        # 构建角色链信息
        role = span.attributes.get("agent_role", "")
        from_role = span.attributes.get("from_role", "")
        role_prefix = f"[{from_role} → {role}] " if from_role else f"[{role}] " if role else ""

        # 构建关键属性摘要
        key_attrs = {}
        for k in ("action_type", "delegate_to", "tool_name", "task_preview"):
            v = span.attributes.get(k)
            if v is not None:
                key_attrs[k] = v

        attrs_str = str(key_attrs) if key_attrs else str(span.attributes)
        _log.info(
            "trace_span",
            span_name=span.name,
            role_prefix=role_prefix,
            status=span.status,
            dur_ms=dur,
            attrs=attrs_str,
        )
