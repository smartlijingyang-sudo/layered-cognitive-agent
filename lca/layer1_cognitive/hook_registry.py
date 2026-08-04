"""SimpleHookRegistry — lifecycle hooks.

Cognitive loop phases are observed at the trigger boundary via Telemetry
(``span``), so Runtime stays free of sink/backend concerns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from lca.contracts.protocols import HookRegistry, Observability
from lca.contracts.state import AgentState
from lca.contracts.telemetry import ATTR_STEP, HOOK_TO_PHASE_SPAN, SpanName
from lca.layer0_infra.observability import set_actor, span
from lca.layer0_infra.observability.redaction import safe_repr
from lca.layer0_infra.observability.span_attributes import extract_span_attributes

_log = structlog.get_logger("lca.hook_registry")


def _span_name_for_hook(event_name: str) -> str:
    if event_name in HOOK_TO_PHASE_SPAN:
        return HOOK_TO_PHASE_SPAN[event_name]
    if event_name == "on_error":
        return SpanName.ERROR.value
    return f"hook.{event_name}"


class SimpleHookRegistry(HookRegistry):
    """Register and fire lifecycle hooks; emit phase spans via ambient Telemetry."""

    def __init__(self, observability: Observability) -> None:
        self._hooks: dict[str, list[Callable]] = {}
        # Kept for composition / tests that read the sink; emission uses ambient Telemetry.
        self.observability = observability

    def register(self, event_name: str, hook: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> Any:
        # Ambient actor identity so nested llm.chat / tool / transport spans are
        # self-describing (ADR-0032); the loop itself stays observability-free.
        set_actor(state.agent_role, state.step)
        attrs = extract_span_attributes(event_name, kwargs)
        attrs[ATTR_STEP] = state.step
        if state.agent_role:
            attrs.setdefault("agent_role", state.agent_role)
        with span(_span_name_for_hook(event_name), **attrs):
            for hook in self._hooks.get(event_name, []):
                await hook(event_name, state, **kwargs)
        return None


async def default_logging_hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    role_info = f"role={state.agent_role}" if state.agent_role else ""
    delegator_info = f"from_role={state.from_role}" if state.from_role else ""
    context_parts = [p for p in [role_info, delegator_info] if p]
    context_str = " ".join(context_parts)
    safe_extra = {k: safe_repr(v) for k, v in extra.items()} if extra else None
    # Progress is on ConsoleObservability spans; keep this at debug to avoid double noise.
    _log.debug(
        "hook_triggered",
        hook_event=event_name,
        step=state.step,
        context=context_str or None,
        hook_extra=safe_extra,
    )
