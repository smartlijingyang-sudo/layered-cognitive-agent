"""SimpleHookRegistry —— 生命周期钩子管理。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from contracts.state import TypedState
from contracts.observability import TraceSpan
from contracts.protocols import Observability, HookRegistryP, Hook


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleHookRegistry(HookRegistryP):
    """注册和触发生命周期钩子。"""

    def __init__(self, observability: Observability) -> None:
        self._hooks: dict[str, list[Callable]] = {}
        self.observability = observability

    def register(self, event_name: str, hook: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any:
        span = TraceSpan(
            span_id=_new_id("span"),
            trace_id=state.trace_id,
            name=f"hook.{event_name}",
            started_at=_now(),
        )
        for hook in self._hooks.get(event_name, []):
            await hook(event_name, state, **kwargs)
        span.ended_at = _now()
        self.observability.emit_span(span)
        return None


async def default_logging_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    print(f"  [Hook] {event_name} @step={state.step} {extra if extra else ''}")
