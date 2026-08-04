"""TeamStrategyRegistry —— 按 strategy key 注册和解析编排策略。

L3：将 ``pipeline`` / ``lead`` / ``fan_out`` 等键映射到 ``TeamStrategy`` 工厂，
消除 if/elif 分发。工厂在 ``resolve`` 时接收用户声明的 Coordination
（lead 路径为 None），参数化策略（Swarm / Debate / Graph）从中提取
max_rounds / execution_graph 等构造参数（ADR-0033）。

无全局单例；实例归 ``Registries.orchestration``，由 TeamComposer 持有。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import TeamStrategy
from lca.contracts.team_coordination import Coordination
from lca.layer0_infra.component_registry import NamedRegistry

OrchestrationFactory = Callable[[Coordination | None], TeamStrategy]


class TeamStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 TeamStrategy 工厂。"""

    _REGISTRY_KIND = "编排策略"

    def resolve(  # type: ignore[override]
        self,
        name: str,
        coordination: Coordination | None = None,
    ) -> TeamStrategy:
        factory = super().resolve(name)
        return factory(coordination)

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self
