"""TeamStrategyRegistry —— 按 strategy key 注册和解析编排策略。

L3：将 ``pipeline`` / ``lead`` / ``fan_out`` 等键映射到 ``TeamStrategy`` 工厂，
消除 if/elif 分发。工厂在 ``resolve`` 时接收组合期闭合的 TeamAssembly
（governance / stage / lead），从中取所需闭合策略——所有治理方式（含 lead）
走同一条注册表路径（ADR-0034）。

无全局单例；实例归 ``Registries.orchestration``，由 ``spawn_team`` 持有。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import TeamAssembly, TeamStrategy
from lca.infrastructure.component_registry import NamedRegistry

OrchestrationFactory = Callable[[TeamAssembly], TeamStrategy]


class TeamStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 TeamStrategy 工厂。"""

    _REGISTRY_KIND = "编排策略"

    def register(self, name: str, impl: OrchestrationFactory) -> None:
        if name in self:
            raise KeyError(f"编排策略: {name!r} already registered")
        super().register(name, impl)

    def resolve(self, name: str, assembly: TeamAssembly) -> TeamStrategy:  # type: ignore[override]
        factory = super().resolve(name)
        return factory(assembly)

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self
