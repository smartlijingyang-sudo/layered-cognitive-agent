"""Coding Agent Tools 默认实现 —— ADR-0065 §六 / PR-8。

每个工具实现 thin wrapper 到 ``TraceInspector`` 已有方法;**绝不写账本**。
"""

from lca.plugins.tools.diagnostics.diff.diff_context import DiffContext
from lca.plugins.tools.diagnostics.failure.failure_explainer import (
    FailureExplainer,
)
from lca.plugins.tools.diagnostics.minimal.minimal_reproduction import (
    MinimalReproduction,
)
from lca.plugins.tools.diagnostics.optimization.optimization_finder import (
    OptimizationFinder,
)
from lca.plugins.tools.diagnostics.plugin.plugin_graph_renderer import (
    PluginGraphRenderer,
)
from lca.plugins.tools.diagnostics.run.run_diff import RunDiffToolAdapter
from lca.plugins.tools.diagnostics.trace.trace_inspector_tool import (
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
