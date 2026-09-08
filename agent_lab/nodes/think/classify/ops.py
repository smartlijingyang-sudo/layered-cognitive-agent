"""classify ops — LLMResponse artifact → lab Decision dict.

Owns DefaultDecisionClassifier semantics and use_tool → call_tool mapping.
"""

from __future__ import annotations

import uuid
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

_LAB_ACTION_MAP = {
    "use_tool": "call_tool",
    "call_tool": "call_tool",
    "respond": "respond",
    "refuse": "refuse",
    "delegate": "delegate",
    "handoff": "handoff",
    "stop": "stop",
    "ask_human": "ask_human",
}


def classify_response(
    response_artifact: Artifact | None,
    *,
    classifier: Any | None = None,
) -> Artifact:
    response = _response_from_artifact(response_artifact)
    clf = classifier if classifier is not None else _default_classifier()
    decision = clf.classify(response)
    return Artifact(
        kind=ArtifactKind.FACT,
        content=_decision_to_lab_dict(decision),
        schema_ref="decision.v1",
    )


def _default_classifier() -> Any:
    from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier

    return DefaultDecisionClassifier()


def _response_from_artifact(artifact: Artifact | None) -> Any:
    from lca.contracts.models.core.conversation.llm import (
        LLMResponse,
        NativeToolCall,
        TokenUsage,
    )

    if artifact is None or artifact.content is None:
        return LLMResponse(text="", tool_calls=[])
    content = artifact.content
    if isinstance(content, dict):
        text = str(content.get("text") or content.get("content") or "")
        raw_calls = content.get("tool_calls") or []
        model = str(content.get("model") or "")
        finish_reason = content.get("finish_reason")
        usage_raw = content.get("usage")
    else:
        text = str(content)
        raw_calls = []
        model = ""
        finish_reason = None
        usage_raw = None

    tool_calls: list[NativeToolCall] = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            tool_calls.append(
                NativeToolCall(
                    call_id=str(tc.get("id") or tc.get("call_id") or ""),
                    name=str(tc.get("name") or tc.get("tool_name") or ""),
                    arguments=dict(tc.get("arguments") or tc.get("args") or {}),
                )
            )
            continue
        tool_calls.append(
            NativeToolCall(
                call_id=str(getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""),
                name=str(getattr(tc, "name", "") or getattr(tc, "tool_name", "") or ""),
                arguments=dict(getattr(tc, "arguments", {}) or {}),
            )
        )

    usage = None
    if isinstance(usage_raw, dict):
        usage = TokenUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
        )
    return LLMResponse(
        text=text,
        model=model,
        usage=usage,
        finish_reason=finish_reason,
        tool_calls=tool_calls,
    )


def _decision_to_lab_dict(decision: Any) -> dict[str, Any]:
    raw_type = str(getattr(decision, "action_type", "") or "respond")
    action_type = _LAB_ACTION_MAP.get(raw_type, raw_type)
    tool_calls = []
    for tc in getattr(decision, "tool_calls", None) or []:
        tool_calls.append(
            {
                "call_id": getattr(tc, "call_id", "") or "",
                "name": getattr(tc, "tool_name", None) or getattr(tc, "name", "") or "",
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
        )
    delegations = []
    for d in getattr(decision, "delegations", None) or []:
        if hasattr(d, "subtask"):
            delegations.append(
                {
                    "subtask": d.subtask,
                    "target_role": d.target_role,
                    "target_agent_id": d.target_agent_id,
                }
            )
            continue
        if isinstance(d, dict):
            delegations.append(dict(d))
    conf = getattr(decision, "confidence", None)
    return {
        "decision_id": getattr(decision, "decision_id", "") or f"dec_{uuid.uuid4().hex[:12]}",
        "action_type": action_type,
        "rationale": getattr(decision, "rationale", "") or "",
        "confidence": float(1.0 if conf is None else conf),
        "tool_calls": tool_calls,
        "delegations": delegations,
        "response_text": getattr(decision, "response_text", None),
        "degraded_from": getattr(decision, "degraded_from", None),
        "extra": dict(getattr(decision, "extra", {}) or {}),
    }
