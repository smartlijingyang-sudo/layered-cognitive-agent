"""CordisHookRegistry —— 生命周期钩子的 cordis events namespace 投影。

每个 ``HookEvent`` 映射到 cordis ``events.serial(f"hook/{event.value}", ...)``；
外部调用 ``await hooks.trigger(event, state, **kwargs)`` 转发到 cordis events。
相位 span 在 trigger 边界统一发射（观察者模式），属性从 hook kwargs 提取后
经 ambient 策略脱敏/截断（写入期强制）。

设计：把生命周期钩子作为 cordis events 暴露（``agent/pre-step`` 、
``tools/pre-execute`` 等都是 ``ctx.on`` 的 listener）。LCA 把 ``HookEvent``
枚举映射成 ``hook/<event>`` 命名空间，单一 dispatch 后端——cordis events。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.atoms.telemetry import ATTR_STEP, HOOK_TO_PHASE_SPAN, SpanName
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.contracts.protocols import HookRegistry
from lca.infrastructure.observability import detached_span, record_runtime, set_actor

_log = structlog.get_logger(__name__)


def _span_name_for_hook(event_name: str) -> str:
    if event_name in HOOK_TO_PHASE_SPAN:
        return HOOK_TO_PHASE_SPAN[event_name]
    if event_name == HookEvent.ON_ERROR:
        return SpanName.ERROR.value
    return f"hook.{event_name}"


def _extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract attributes from a hook payload without bypassing policy enforcement."""
    attrs: dict[str, Any] = {"event": event_name}

    state = kwargs.get("state")
    if state is not None:
        if getattr(state, "agent_role", ""):
            attrs["agent_role"] = state.agent_role
        if getattr(state, "from_role", ""):
            attrs["from_role"] = state.from_role
        if getattr(state, "task", ""):
            attrs["task_preview"] = str(state.task)

    decision = kwargs.get("decision")
    if decision is not None:
        attrs["action_type"] = getattr(decision, "action_type", str(decision))
        confidence = getattr(decision, "confidence", None)
        if confidence is not None:
            attrs["confidence"] = confidence
        if getattr(decision, "response_text", ""):
            attrs["response_preview"] = str(decision.response_text)
        if getattr(decision, "tool_name", ""):
            attrs["tool_name"] = decision.tool_name
        delegations = getattr(decision, "delegations", None) or []
        if delegations:
            first = delegations[0]
            target = getattr(first, "target_role", None) or getattr(first, "target_agent_id", None)
            if target:
                attrs["delegate_target"] = target
            if len(delegations) > 1:
                attrs["delegate_count"] = len(delegations)

    error = kwargs.get("error")
    if error is not None:
        attrs["error_type"] = type(error).__name__
        attrs["error_message"] = str(error)

    observation = kwargs.get("observation")
    if observation is not None:
        attrs["observation_success"] = getattr(observation, "success", None)

    reflection = kwargs.get("reflection")
    if reflection is not None:
        attrs["reflection_preview"] = str(reflection)

    return attrs


class CordisHookRegistry(HookRegistry):
    """Lifecycle hooks as a typed projection of cordis events.

    Each ``HookEvent`` value maps to ``hook/<event>`` in the cordis events
    namespace; ``trigger`` dispatches through ``ctx.events.serial`` (last-
    listener-wins — standard for lifecycle hooks: each returns its own
    continuation, the framework ignores the return value when no listener
    transforms it). Phase spans fire at the trigger boundary.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def register(self, event_name: str, hook: Callable) -> None:
        """Register a hook for *event_name* via cordis events."""
        self._ctx.events.on(_hook_event_name(event_name), hook)

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> Any:
        # Ambient actor: nested llm/tool/memory span auto-tags, runtime body zero telemetry.
        set_actor(state.agent_role, state.step)
        attrs = _extract_span_attributes(event_name, {"state": state, **kwargs})
        attrs[ATTR_STEP] = state.step
        # cordis events.serial / parallel / waterfall only accept positional
        # payloads; we fold state + kwargs into a single envelope so the
        # listener signature stays uniform across all 5 dispatch modes.
        envelope = {"event_name": event_name, "state": state, **kwargs}
        record_runtime(
            DiagnosticCategory.HOOK,
            "hook.trigger",
            plugin="hook_registry.simple",
            attributes={
                "hook_event": event_name,
                "listener_namespace": _hook_event_name(event_name),
                "state_step": state.step,
            },
        )
        with detached_span(_span_name_for_hook(event_name), **attrs):
            return await self._ctx.events.serial(_hook_event_name(event_name), envelope)


def _hook_event_name(event_name: str) -> str:
    """Namespace hook events so they cannot collide with plugin events."""
    if event_name.startswith("hook/"):
        return event_name
    return f"hook/{event_name}"


def _safe_repr(value: Any) -> Any:
    """结构化日志安全表示：原语透传，复杂对象 fallback ``repr()``。"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return repr(value)


async def default_logging_hook(envelope: Any) -> None:
    """Default hook listener — accepts the cordis envelope directly.

    The listener is invoked with a single positional argument (the cordis
    event envelope), not the legacy ``(event_name, state, **kwargs)`` triple.
    Production hooks that prefer the legacy shape should wrap themselves.
    """
    if not isinstance(envelope, dict):
        _log.debug("hook_triggered", hook_event="<unknown>", payload=_safe_repr(envelope))
        return
    state_raw = envelope.get("state")
    state: Any = state_raw  # narrow to Any to silence state-shape mismatches
    event_name = envelope.get("event_name", "?")
    extra = {k: v for k, v in envelope.items() if k != "state"}
    agent_role_val = state.agent_role if state is not None and hasattr(state, "agent_role") else ""
    from_role_val = state.from_role if state is not None and hasattr(state, "from_role") else ""
    role_info = f"role={agent_role_val}" if agent_role_val else ""
    delegator_info = f"from_role={from_role_val}" if from_role_val else ""
    context_parts = [p for p in [role_info, delegator_info] if p]
    context_str = " ".join(context_parts)
    safe_extra = {k: _safe_repr(v) for k, v in extra.items()} if extra else None
    _log.debug(
        "hook_triggered",
        hook_event=event_name,
        step=getattr(state, "step", None) if state is not None else None,
        context=context_str or None,
        hook_extra=safe_extra,
    )


def cordis_hook_registry(ctx: Any) -> CordisHookRegistry:
    """Return a :class:`CordisHookRegistry` wrapping *ctx*."""
    return CordisHookRegistry(ctx)


__all__ = [
    "CordisHookRegistry",
    "cordis_hook_registry",
]
