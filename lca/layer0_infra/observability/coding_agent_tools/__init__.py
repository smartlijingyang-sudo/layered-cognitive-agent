"""Coding Agent Tools 默认实现 —— ADR-0065 §六 / PR-8。

每个工具实现 thin wrapper 到 ``TraceInspector`` 已有方法;**绝不写账本**。
"""

from lca.layer0_infra.observability.coding_agent_tools.diff_context import DiffContext
from lca.layer0_infra.observability.coding_agent_tools.failure_explainer import (
    FailureExplainer,
)
from lca.layer0_infra.observability.coding_agent_tools.minimal_reproduction import (
    MinimalReproduction,
)
from lca.layer0_infra.observability.coding_agent_tools.optimization_finder import (
    OptimizationFinder,
)
from lca.layer0_infra.observability.coding_agent_tools.plugin_graph_renderer import (
    PluginGraphRenderer,
)
from lca.layer0_infra.observability.coding_agent_tools.run_diff import RunDiffToolAdapter
from lca.layer0_infra.observability.coding_agent_tools.trace_inspector_tool import (
    TraceInspectorToolAdapter,
)

__all__ = [
    "DiffContext",
    "FailureExplainer",
    "MinimalReproduction",
    "OptimizationFinder",
    "PluginGraphRenderer",
    "RunDiffToolAdapter",
    "TraceInspectorToolAdapter",
]
