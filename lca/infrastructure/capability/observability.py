"""observability seam Definition — owns ctx.observability."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.protocols import ObservabilityBackend
from lca.infrastructure.capability.dispatch import ProviderDispatch

ObservabilityFactory = Callable[..., ObservabilityBackend]


class ObservabilityService:
    """Service Definition：可观测后端工厂。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[ObservabilityFactory]("observability")

    def register(self, name: str, factory: ObservabilityFactory, *, activate: bool = False) -> None:
        self.providers.register(name, factory, activate=activate)

    def create(self, **kwargs: Any) -> ObservabilityBackend:
        return self.providers.current()(**kwargs)
