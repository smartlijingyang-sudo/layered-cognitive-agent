"""SimpleHookRegistry —— 生命周期钩子 + 认知相位 span 的触发边界。

认知循环本体零遥测：相位 span 在此边界统一发射（观察者模式），
属性从 hook kwargs 提取后经 ambient 策略脱敏/截断（写入期强制）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from lca.contracts.enums import HookEvent
from lca.contracts.protocols import HookRegistry
from lca.contracts.state import AgentState
from lca.contracts.telemetry import ATTR_STEP, HOOK_TO_PHASE_SPAN, SpanName
from lca.layer0_infra.observability import set_actor, span

_log = structlog.get_logger("lca.hook_registry")


def _span_name_for_hook(event_name: str) -> str:
    if event_name in HOOK_TO_PHASE_SPAN:
        return HOOK_TO_PHASE_SPAN[event_name]
    if event_name == HookEvent.ON_ERROR:
        return SpanName.ERROR.value
    return f"hook.{event_name}"


def _extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 hook kwargs 提取属性（原值；脱敏/截断由属性策略在写入期强制）。"""
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


class SimpleHookRegistry(HookRegistry):
    """注册并触发生命周期钩子；相位 span 经 ambient Telemetry 发射。"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, event_name: str, hook: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> Any:
        # Ambient actor 身份：嵌套 llm/tool/memory span 自动盖章，循环本体零遥测。
        set_actor(state.agent_role, state.step)
        attrs = _extract_span_attributes(event_name, kwargs)
        attrs[ATTR_STEP] = state.step
        with span(_span_name_for_hook(event_name), **attrs):
            for hook in self._hooks.get(event_name, []):
                await hook(event_name, state, **kwargs)
        return None


def _safe_repr(value: Any) -> Any:
    """结构化日志安全表示：原语透传，复杂对象 fallback ``repr()``。"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return repr(value)


async def default_logging_hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    role_info = f"role={state.agent_role}" if state.agent_role else ""
    delegator_info = f"from_role={state.from_role}" if state.from_role else ""
    context_parts = [p for p in [role_info, delegator_info] if p]
    context_str = " ".join(context_parts)
    safe_extra = {k: _safe_repr(v) for k, v in extra.items()} if extra else None
    # 进度展示由 span 叙述承担；此处仅 debug 级，避免双份噪音。
    _log.debug(
        "hook_triggered",
        hook_event=event_name,
        step=state.step,
        context=context_str or None,
        hook_extra=safe_extra,
    )
