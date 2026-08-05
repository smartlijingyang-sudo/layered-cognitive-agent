"""Console 叙事渲染 —— 纯函数集合（包内私有，仅经包根导出公共辅助）。"""

from lca.layer0_infra.observability.narrative.plan_narrative import (
    format_run_plan_card,
    plan_steps_joined,
    strategy_plan_steps,
)
from lca.layer0_infra.observability.narrative.run_narrative import (
    format_section_header,
    format_span_line,
    is_milestone_span,
    logical_depth,
    section_key_for_span,
)

__all__ = [
    "format_run_plan_card",
    "format_section_header",
    "format_span_line",
    "is_milestone_span",
    "logical_depth",
    "plan_steps_joined",
    "section_key_for_span",
    "strategy_plan_steps",
]
