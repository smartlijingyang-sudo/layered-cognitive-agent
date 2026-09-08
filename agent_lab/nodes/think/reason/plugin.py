"""think.reason — call the LLM on exposed messages.

Sole I/O seam inside the think phase. Does not parse Decisions or run gates.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter


@node(
    id="think.reason",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call OpenAICompatAdapter.complete on exposed messages; "
        "emit an LLMResponse-shaped MESSAGE artifact."
    ),
    inputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("response", kind=PortKind.MESSAGE)],
    provides=["llm_response"],
    requires=["think_messages"],
    emits=["llm_call"],
    relates_to=["think.expose", "think.classify"],
)
class ThinkReason(Node):
    name = "think.reason"

    def execute(self, node, inputs):
        src = node.config.get("from", "messages")
        out = node.config.get("to", "response")
        src_a = inputs.get(src) or inputs.get("messages")
        messages = _as_messages(src_a)
        prompt, history = _split_prompt_history(messages)

        adapter_kwargs = dict(node.config.get("adapter_kwargs", {}) or {})
        adapter = OpenAICompatAdapter(**adapter_kwargs)
        if history:
            response = asyncio.run(adapter.complete(prompt, history=history))
        else:
            response = asyncio.run(adapter.complete(prompt))

        text = getattr(response, "text", "") or ""
        tool_calls = _tool_calls_to_dicts(getattr(response, "tool_calls", None) or [])
        payload: dict[str, Any] = {
            "text": text,
            "content": text,
            "role": "assistant",
            "model": getattr(response, "model", "") or "",
            "tool_calls": tool_calls,
            "finish_reason": getattr(response, "finish_reason", None),
        }
        return {
            out: Artifact(
                kind=ArtifactKind.MESSAGE,
                content=payload,
                schema_ref="llm.response.v1",
            )
        }


def _as_messages(art: Artifact | None) -> list[dict[str, Any]]:
    if art is None:
        return []
    content = art.content
    if isinstance(content, list):
        return [dict(m) for m in content if isinstance(m, dict)]
    if isinstance(content, dict) and isinstance(content.get("messages"), list):
        return [dict(m) for m in content["messages"] if isinstance(m, dict)]
    return []


def _split_prompt_history(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Last user content is the prompt; earlier messages are history."""
    if not messages:
        return "", []
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        # No user turn — flatten all text into the prompt.
        parts = [
            str(m.get("content", ""))
            for m in messages
            if isinstance(m.get("content"), str) and m.get("content")
        ]
        return "\n".join(parts), []
    prompt = str(messages[last_user_idx].get("content") or "")
    history = messages[:last_user_idx]
    return prompt, history


def _tool_calls_to_dicts(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            out.append(
                {
                    "id": str(tc.get("id") or tc.get("call_id") or ""),
                    "call_id": str(tc.get("call_id") or tc.get("id") or ""),
                    "name": str(tc.get("name") or tc.get("tool_name") or ""),
                    "arguments": dict(tc.get("arguments") or tc.get("args") or {}),
                }
            )
            continue
        out.append(
            {
                "id": str(getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""),
                "call_id": str(getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""),
                "name": str(getattr(tc, "name", "") or getattr(tc, "tool_name", "") or ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
        )
    return out
