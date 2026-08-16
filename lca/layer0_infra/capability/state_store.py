"""state_store seam Definition."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.protocols import StateStore
from lca.layer0_infra.capability.dispatch import ProviderDispatch

StateStoreFactory = Callable[..., StateStore]


class StateStoreService:
    """Service Definition：StateStore 工厂表。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[StateStoreFactory]("state_store")

    def register(self, name: str, factory: StateStoreFactory, *, activate: bool = False) -> None:
        self.providers.register(name, factory, activate=activate)

    def create(self, **kwargs: Any) -> StateStore:
        return self.providers.current()(**kwargs)
