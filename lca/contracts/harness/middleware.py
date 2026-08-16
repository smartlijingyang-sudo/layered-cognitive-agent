"""Phase middleware SPI (spec §2.2.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lca.contracts.harness.plugin import ExtensionPoint


@dataclass(frozen=True)
class MiddlewareRegistration:
    seam_key: str
    priority: int = 100
    plugin_id: str = ""


class PhaseContext(Protocol):
    @property
    def session_id(self) -> str: ...

    def record(self, event_data: Any) -> None: ...


class PhaseMiddleware(Protocol):
    async def __call__(self, phase: str, state: Any, context: PhaseContext) -> Any: ...


class MiddlewareRegistry(Protocol):
    def register_point(self, point: ExtensionPoint) -> None: ...

    def register(
        self, registration: MiddlewareRegistration, middleware: PhaseMiddleware
    ) -> None: ...

    async def run(
        self,
        seam_key: str,
        phase: str,
        state: Any,
        context: PhaseContext,
    ) -> Any: ...

    def has_point(self, seam_key: str) -> bool: ...

    def list_registrations(self, seam_key: str) -> list[MiddlewareRegistration]: ...
