"""OrchestrationStrategyRegistry —— 按 process 名称注册和解析编排策略。"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import OrchestrationStrategy
from lca.layer0_infra.component_registry import NamedRegistry

OrchestrationFactory = Callable[[], OrchestrationStrategy]

_global_orchestration_registry: OrchestrationStrategyRegistry | None = None


class OrchestrationStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 OrchestrationStrategy 工厂。

    工厂签名: () -> OrchestrationStrategy
    策略实例在 run() 时通过 OrchestrationContext 获取运行时数据。
    """

    _REGISTRY_KIND = "编排策略"

    def resolve(self, name: str) -> OrchestrationStrategy:  # type: ignore[override]
        # 有意将返回类型从 Factory 变为 Strategy 实例
        factory = super().resolve(name)
        return factory()

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self


def get_global_orchestration_registry() -> OrchestrationStrategyRegistry:
    global _global_orchestration_registry
    if _global_orchestration_registry is None:
        _global_orchestration_registry = OrchestrationStrategyRegistry()
    return _global_orchestration_registry
