"""Phase middleware SPI (spec §2.2.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol


@dataclass(frozen=True)
class MiddlewareRegistration:
    """One middleware binding to a cognitive phase event.

    `callback` is OPTIONAL (default None) to preserve the existing 3-field
    constructor signature used at 4 production callers (F1 fix):
    - lca/plugins/budget_policy/__init__.py:55
    - lca/plugins/loop_intervention_policy/__init__.py:55
    - lca/layer2_runtime/hook_middleware.py:57
    - lca/layer2_runtime/loop_intervention_mw.py:47

    These callers pass seam_key/priority/plugin_id only — the actual callback
    is registered separately via `InMemoryMiddlewareRegistry.register()`.
    """

    seam_key: str
    priority: int = 100
    plugin_id: str = ""
    callback: Optional[Callable[..., Awaitable[Any]]] = None
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
