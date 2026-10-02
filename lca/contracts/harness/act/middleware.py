"""Phase middleware SPI (spec §2.2.5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class MiddlewareRegistration:
    """One middleware binding to a cognitive phase event.

    `callback` is OPTIONAL (default None): registrations carry
    seam_key/priority/plugin_id only — the actual callback
    is registered separately via `InMemoryMiddlewareRegistry.register()`.
    """

    seam_key: str
    priority: int = 100
    plugin_id: str = ""
    callback: Callable[..., Awaitable[Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PhaseContext(Protocol):
    @property
    def session_id(self) -> str: ...

    def record(self, event_data: Any) -> None: ...


class PhaseMiddleware(Protocol):
    async def __call__(self, phase: str, state: Any, context: PhaseContext) -> Any: ...


# Dropped (cordis migration):
# - MiddlewareRegistry Protocol (references ExtensionPoint; replaced by
#   cordis.ctx.events.on() hooks in plugin setup)
# - callback field required → now optional (default None)
