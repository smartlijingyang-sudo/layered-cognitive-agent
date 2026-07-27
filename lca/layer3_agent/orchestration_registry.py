"""OrchestrationStrategyRegistry —— 按 process 名称注册和解析编排策略。"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import OrchestrationStrategy

OrchestrationFactory = Callable[[], OrchestrationStrategy]

_global_orchestration_registry: OrchestrationStrategyRegistry | None = None


class OrchestrationStrategyRegistry:
    """按名称注册和查找 OrchestrationStrategy 工厂。

    工厂签名: () -> OrchestrationStrategy
    策略实例在 run() 时通过 OrchestrationContext 获取运行时数据。
    """

    def __init__(self) -> None:
        self._factories: dict[str, OrchestrationFactory] = {}

    def register(self, name: str, factory: OrchestrationFactory) -> None:
        self._factories[name] = factory

    def resolve(self, name: str) -> OrchestrationStrategy:
        factory = self._factories.get(name)
        if factory is None:
            available = self.list_strategies()
            raise ValueError(f"未注册编排策略 {name!r}，可用策略: {available}")
        return factory()

    def list_strategies(self) -> list[str]:
        return list(self._factories.keys())

    def has(self, name: str) -> bool:
        return name in self._factories


def get_global_orchestration_registry() -> OrchestrationStrategyRegistry:
    global _global_orchestration_registry
    if _global_orchestration_registry is None:
        _global_orchestration_registry = OrchestrationStrategyRegistry()
    return _global_orchestration_registry
