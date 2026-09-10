"""v2 plan marker — Bundle Graph Schema v2 plan 形态识别。

ADR-0218 §3.1。

本模块职责:**只**提供 plan 形态识别的 Protocol。
- 不存数据,不做事,不变更 CompiledRunPlan 字段
- BundleSubgraphResolver 在 v2 路径返回 CompiledRunPlan 时同时实现本 Protocol
- interpreter 用 isinstance(_, V2BundleGraphPlanMarker) 识别 v2 分支

为什么用 Protocol 不用字段标记:
- CompiledRunPlan 是 frozen dataclass,加 Protocol 不侵入字段(C13 不变量)
- provenance 字符串是观察面字段,不应承担控制面路由(C7 分离)
- Protocol 是运行时类型契约,不需 import-linter 改 graph(C6 最小化)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphSpec,
)


@runtime_checkable
class V2BundleGraphPlanMarker(Protocol):
    """v2 plan 标记。

    实现此 Protocol 表示 CompiledRunPlan 来自 Bundle Graph Schema v2 路径
    (ADR-0217),interpreter 应当走 v2 调度分支而非老 declarative 路径。
    """

    def get_bundle_graph_spec(self) -> BundleGraphSpec:
        """返回 v2 plan 的原始 BundleGraphSpec。

        BundleSubgraphResolver._compile_bundle_graph 在 _wrap_compiled_run_plan
        阶段把 spec 嵌入返回的 CompiledRunPlan;NodeGraphDriver 读这个 spec
        作为调度循环输入。
        """
        ...


__all__ = ["V2BundleGraphPlanMarker"]
