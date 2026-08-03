"""TeamStrategyRegistry —— 按 strategy key 注册和解析编排策略。

L3：将 ``pipeline`` / ``lead`` / ``fan_out`` 等键映射到 ``TeamStrategy`` 工厂，
消除 if/elif 分发。``resolve`` 调用工厂后返回策略实例。

ADR-0024：无全局单例；实例归 ``Registries.orchestration``，由 TeamComposer 持有。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import TeamStrategy
from lca.layer0_infra.component_registry import NamedRegistry

OrchestrationFactory = Callable[[], TeamStrategy]


class TeamStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 TeamStrategy 工厂。"""

    _REGISTRY_KIND = "编排策略"

    def resolve(self, name: str) -> TeamStrategy:  # type: ignore[override]
        factory = super().resolve(name)
        return factory()

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self
