"""StrategyRegistry —— 策略注册表，支持运行时动态切换 Brain 策略。"""

from __future__ import annotations

from typing import Optional


class StrategyRegistry:
    """按名称注册和查找 BrainStrategy 实现。"""

    def __init__(self) -> None:
        self._strategies: dict[str, object] = {}

    def register(self, name: str, strategy: object) -> None:
        self._strategies[name] = strategy

    def resolve(self, name: str) -> Optional[object]:
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())
