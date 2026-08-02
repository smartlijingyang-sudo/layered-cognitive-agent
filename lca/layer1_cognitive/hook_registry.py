"""SimpleHookRegistry —— 生命周期钩子注册与触发。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import structlog

from lca.contracts.ids import new_id
from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import HookRegistry, Observability
from lca.contracts.state import AgentState
from lca.layer0_infra.observability.redaction import safe_repr
from lca.layer0_infra.observability.span_attributes import extract_span_attributes

_log = structlog.get_logger("lca.hook_registry")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SimpleHookRegistry(HookRegistry):
    """注册和触发生命周期钩子。"""

    def __init__(self, observability: Observability) -> None:
        self._hooks: dict[str, list[Callable]] = {}
        self.observability = observability

    def register(self, event_name: str, hook: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> Any:
        span = TraceSpan(
            span_id=new_id("span"),
            trace_id=state.trace_id,
            name=f"hook.{event_name}",
            started_at=_now(),
            attributes=extract_span_attributes(event_name, kwargs),
        )
        for hook in self._hooks.get(event_name, []):
            await hook(event_name, state, **kwargs)
        span.ended_at = _now()
        self.observability.emit_span(span)
        return None


async def default_logging_hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    role_info = f"role={state.agent_role}" if state.agent_role else ""
    delegator_info = f"from_role={state.from_role}" if state.from_role else ""
    context_parts = [p for p in [role_info, delegator_info] if p]
    context_str = " ".join(context_parts)
    safe_extra = {k: safe_repr(v) for k, v in extra.items()} if extra else None
    _log.info(
        "hook_triggered",
        hook_event=event_name,
        step=state.step,
        context=context_str or None,
        hook_extra=safe_extra,
    )
