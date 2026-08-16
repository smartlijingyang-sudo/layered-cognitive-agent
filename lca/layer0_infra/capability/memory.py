"""memory seam Definition — factory table; each agent creates an isolated store."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.protocols import MemorySystem
from lca.layer0_infra.capability.dispatch import ProviderDispatch

MemoryFactory = Callable[..., MemorySystem]


class MemoryService:
    """Service Definition：注册 Memory 工厂，Consumer 通过 create() 取实例。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[MemoryFactory]("memory")

    def register(self, name: str, factory: MemoryFactory, *, activate: bool = False) -> None:
        self.providers.register(name, factory, activate=activate)

    def create(self, **kwargs: Any) -> MemorySystem:
        return self.providers.current()(**kwargs)
