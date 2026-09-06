"""No-op HookRegistry — platform lifecycle uses RuntimeLifecycle SSOT."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import HookRegistry


class NullHookRegistry(HookRegistry):
    """Observe-only stub; external ``register_hook`` calls are accepted and ignored."""

    def register(self, event_name: str, hook: Callable[..., Any]) -> None:
        del event_name, hook

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> None:
        del event_name, state, kwargs
        return None


__all__ = ["NullHookRegistry"]
