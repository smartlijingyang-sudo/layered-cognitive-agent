"""SimpleHookRegistry —— 生命周期钩子管理。"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import HookRegistry, Observability
from lca.contracts.state import TypedState


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleHookRegistry(HookRegistry):
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
            attributes=_extract_span_attributes(event_name, kwargs),
        )
        for hook in self._hooks.get(event_name, []):
            await hook(event_name, state, **kwargs)
        span.ended_at = _now()
        self.observability.emit_span(span)
        return None


async def default_logging_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    role_info = f"role={state.agent_role}" if state.agent_role else ""
    delegator_info = f"delegated_by={state.delegated_by}" if state.delegated_by else ""
    context_parts = [p for p in [role_info, delegator_info] if p]
    context_str = " ".join(context_parts)
    prefix = f"[{context_str}] " if context_str else ""
    print(f"  [Hook] {prefix}{event_name} @step={state.step} {extra if extra else ''}")


def _extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 hook kwargs 中提取可观测属性，脱敏后放入 TraceSpan.attributes。"""

    attrs: dict[str, Any] = {"event": event_name}

    # 从 state 中提取角色和委派信息
    state = kwargs.get("state")
    if state is not None:
        if hasattr(state, "agent_role") and state.agent_role:
            attrs["agent_role"] = state.agent_role
        if hasattr(state, "delegated_by") and state.delegated_by:
            attrs["delegated_by"] = state.delegated_by
        if hasattr(state, "task") and state.task:
            attrs["task_preview"] = _truncate(_sanitize(str(state.task)))

    # post_think: 记录决策摘要
    decision = kwargs.get("decision")
    if decision is not None:
        attrs["action_type"] = getattr(decision, "action_type", str(decision))
        attrs["confidence"] = getattr(decision, "confidence", None)
        if hasattr(decision, "response_text") and decision.response_text:
            attrs["response_preview"] = _truncate(_sanitize(str(decision.response_text)))
        if hasattr(decision, "tool_name") and decision.tool_name:
            attrs["tool_name"] = decision.tool_name
        # 委派目标
        delegate_to = getattr(decision, "delegate_to", None)
        if delegate_to is not None:
            target = getattr(delegate_to, "target_role", None) or getattr(
                delegate_to, "target_agent_id", None
            )
            if target:
                attrs["delegate_to"] = target

    # on_error: 记录错误信息
    error = kwargs.get("error")
    if error is not None:
        attrs["error_type"] = type(error).__name__
        attrs["error_message"] = _truncate(str(error))

    # observation / reflection
    observation = kwargs.get("observation")
    if observation is not None:
        attrs["observation_success"] = getattr(observation, "success", None)

    reflection = kwargs.get("reflection")
    if reflection is not None:
        attrs["reflection_preview"] = _truncate(_sanitize(str(reflection)))

    return attrs


_MAX_PREVIEW_LEN = 200
_SECRET_PATTERN = re.compile(r"(sk-|api[_-]?key[_-]?|token[_-]?)[\w-]{8,}", re.IGNORECASE)


def _truncate(text: str, max_len: int = _MAX_PREVIEW_LEN) -> str:
    """截断过长文本。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _sanitize(text: str) -> str:
    """过滤疑似密钥字符串。"""
    return _SECRET_PATTERN.sub("[REDACTED]", text)
