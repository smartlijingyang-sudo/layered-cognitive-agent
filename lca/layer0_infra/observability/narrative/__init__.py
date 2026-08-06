"""叙事渲染工具集（ADR-0037 后仅存 span 诊断与计划步模板）。

人类视图（场景卡/角色叙事/Run Card/序列图）由 journal 投影器渲染；
本包保留：span 树诊断渲染（run_narrative）与计划步模板（plan_narrative）。
"""

from lca.layer0_infra.observability.narrative.plan_narrative import (
    plan_steps_joined,
    strategy_plan_steps,
)
from lca.layer0_infra.observability.narrative.run_narrative import (
    format_span_line,
    is_milestone_span,
)

__all__ = [
    "format_span_line",
    "is_milestone_span",
    "plan_steps_joined",
    "strategy_plan_steps",
]
