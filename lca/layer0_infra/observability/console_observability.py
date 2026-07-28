"""控制台可观测性实现 —— 把每个跨层调用输出为结构化 TraceSpan。"""

from __future__ import annotations

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability


class ConsoleObservability(Observability):
    """默认可观测实现：结构化 TraceSpan 输出到控制台。"""

    def emit_span(self, span: TraceSpan) -> None:
        dur = None
        if span.ended_at:
            dur = int((span.ended_at - span.started_at).total_seconds() * 1000)

        # 构建角色链信息
        role = span.attributes.get("agent_role", "")
        delegated_by = span.attributes.get("delegated_by", "")
        role_prefix = (
            f"[{delegated_by} → {role}] " if delegated_by else f"[{role}] " if role else ""
        )

        # 构建关键属性摘要
        key_attrs = {}
        for k in ("action_type", "delegate_to", "tool_name", "task_preview"):
            v = span.attributes.get(k)
            if v is not None:
                key_attrs[k] = v

        attrs_str = str(key_attrs) if key_attrs else str(span.attributes)
        print(
            f"  [TraceSpan] {role_prefix}{span.name:<28} status={span.status:<5} "
            f"dur_ms={dur} attrs={attrs_str}"
        )
