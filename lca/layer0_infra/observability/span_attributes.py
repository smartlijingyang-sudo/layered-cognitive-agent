"""从 hook kwargs 中提取 TraceSpan 属性。

将认知层 hook 的上下文信息（state、decision、error 等）
转换为扁平的属性字典，供可观测性后端消费。
所有文本值经过脱敏和截断处理。
"""

from __future__ import annotations

from typing import Any

from lca.layer0_infra.observability.redaction import sanitize, truncate


def extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 hook kwargs 中提取可观测属性，脱敏后放入 TraceSpan.attributes。"""
    attrs: dict[str, Any] = {"event": event_name}

    state = kwargs.get("state")
    if state is not None:
        if hasattr(state, "agent_role") and state.agent_role:
            attrs["agent_role"] = state.agent_role
        if hasattr(state, "from_role") and state.from_role:
            attrs["from_role"] = state.from_role
        if hasattr(state, "task") and state.task:
            attrs["task_preview"] = truncate(sanitize(str(state.task)))

    decision = kwargs.get("decision")
    if decision is not None:
        attrs["action_type"] = getattr(decision, "action_type", str(decision))
        attrs["confidence"] = getattr(decision, "confidence", None)
        if hasattr(decision, "response_text") and decision.response_text:
            attrs["response_preview"] = truncate(sanitize(str(decision.response_text)))
        if hasattr(decision, "tool_name") and decision.tool_name:
            attrs["tool_name"] = decision.tool_name
        delegate_to = getattr(decision, "delegate_to", None)
        if delegate_to is not None:
            target = getattr(delegate_to, "target_role", None) or getattr(
                delegate_to, "target_agent_id", None
            )
            if target:
                attrs["delegate_to"] = target

    error = kwargs.get("error")
    if error is not None:
        attrs["error_type"] = type(error).__name__
        attrs["error_message"] = truncate(str(error))

    observation = kwargs.get("observation")
    if observation is not None:
        attrs["observation_success"] = getattr(observation, "success", None)

    reflection = kwargs.get("reflection")
    if reflection is not None:
        attrs["reflection_preview"] = truncate(sanitize(str(reflection)))

    return attrs
