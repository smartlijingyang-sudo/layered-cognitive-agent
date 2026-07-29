"""StrategyRegistry —— 策略注册表，支持运行时动态切换 Brain 策略。

L2 层职责：
    注册表模式（Registry Pattern）的实现。
    将策略名称映射到 BrainFactory（``(llm, role_profile, tools_desc) -> BrainStrategy``），
    由 CognitiveRuntime 在构造时从注册表解析具体策略，实现策略与运行时的解耦。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import BrainStrategy
from lca.layer0_infra.component_registry import NamedRegistry

BrainFactory = Callable[..., BrainStrategy]

_global_strategy_registry: StrategyRegistry | None = None


class StrategyRegistry(NamedRegistry[BrainFactory]):
    """按名称注册和查找 BrainStrategy 工厂。

    工厂签名: (llm, role_profile, tools_desc) -> BrainStrategy
    """

    _REGISTRY_KIND = "Brain 策略"

    def list_strategies(self) -> list[str]:
        return self.list()


def get_global_strategy_registry() -> StrategyRegistry:
    global _global_strategy_registry
    if _global_strategy_registry is None:
        _global_strategy_registry = StrategyRegistry()
    return _global_strategy_registry
