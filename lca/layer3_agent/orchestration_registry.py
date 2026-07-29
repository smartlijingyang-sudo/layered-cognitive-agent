"""OrchestrationStrategyRegistry —— 按 process 名称注册和解析编排策略。

L3 层职责：
    注册表模式（Registry Pattern）的实现。
    将编排策略名称（如 "hierarchical"、"sequential"）映射到
    OrchestrationStrategy 实例，消除 TeamOrchestrator 中的 if/elif 分发。
    工厂签名 ``() -> OrchestrationStrategy``，resolve 时自动调用工厂。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import OrchestrationStrategy
from lca.layer0_infra.component_registry import NamedRegistry

OrchestrationFactory = Callable[[], OrchestrationStrategy]

_global_orchestration_registry: OrchestrationStrategyRegistry | None = None


class OrchestrationStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 OrchestrationStrategy 工厂。

    工厂签名: ``() -> OrchestrationStrategy``
    策略实例在 ``run()`` 时通过 OrchestrationContext 获取运行时数据。

    ``resolve()`` 有意覆盖基类签名：基类返回工厂（``OrchestrationFactory``），
    本类调用工厂后返回策略实例（``OrchestrationStrategy``），
    这是注册表模式的常见变体——注册的是工厂，消费方拿到的是产品。
    """

    _REGISTRY_KIND = "编排策略"

    def resolve(self, name: str) -> OrchestrationStrategy:  # type: ignore[override]
        # 有意将返回类型从 OrchestrationFactory 变为 OrchestrationStrategy 实例：
        # 注册表存工厂，resolve 调用工厂返回产品，消费方无需知道工厂细节。
        factory = super().resolve(name)
        return factory()

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self


def get_global_orchestration_registry() -> OrchestrationStrategyRegistry:
    """返回全局单例编排策略注册表。"""
    global _global_orchestration_registry
    if _global_orchestration_registry is None:
        _global_orchestration_registry = OrchestrationStrategyRegistry()
    return _global_orchestration_registry
