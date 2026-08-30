"""Parse OpenAI ChatCompletion SSE the way LobeHub's native openai.ts mapper does.

This is a field contract, not a second encoder: it only concatenates
``delta.content``, ``delta.reasoning_content``, and ``delta.tool_calls``,
and records the ``[DONE]`` sentinel. Custom ``event:`` names and
evidence-digest indirection (``content_ref``) are failures for the UI wire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LobeHubOpenAIView:
    """Projection LobeHub StreamingHandler actually consumes from the wire."""

    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reasons: list[str] = field(default_factory=list)
    done: bool = False
    chunks: list[dict[str, Any]] = field(default_factory=list)
    custom_event_names: list[str] = field(default_factory=list)
    digest_indirect_frames: list[str] = field(default_factory=list)


def parse_lobehub_openai_sse(raw: bytes | str) -> LobeHubOpenAIView:
    """Split ``data:`` / ``event:`` frames and collect LobeHub-native fields."""

    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    view = LobeHubOpenAIView()
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if event_name and event_name not in {"", "message"}:
            view.custom_event_names.append(event_name)
        payload = "\n".join(data_lines)
        if not payload:
            continue
        if payload == "[DONE]":
            view.done = True
            continue
        try:
            frame = json.loads(payload)
        except json.JSONDecodeError:
            continue
        dumped = json.dumps(frame, ensure_ascii=False)
        if "content_ref" in dumped or '"digest"' in dumped:
            view.digest_indirect_frames.append(dumped)
        view.chunks.append(frame)
        choices = frame.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            continue
        choice = choices[0]
        reason = choice.get("finish_reason")
        if isinstance(reason, str) and reason:
            view.finish_reasons.append(reason)
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        content = delta.get("content")
        if isinstance(content, str) and content:
            view.content += content
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            view.reasoning_content += reasoning
        tools = delta.get("tool_calls")
        if isinstance(tools, list):
            view.tool_calls.extend(item for item in tools if isinstance(item, dict))
    return view


def lobehub_llm_result_would_call_tool(view: LobeHubOpenAIView) -> bool:
    """True when native GeneralChatAgent would emit call_tool / call_tools_batch.

    ``callLlmFinalizer`` sets ``hasToolsCalling`` from
    ``output.toolsCalling.length > 0``
    (``packages/agent-runtime/src/executors/callLlmFinalizer.ts``).
    ``GeneralChatAgent`` ``llm_result`` then issues ``call_tool`` when both
    ``hasToolsCalling`` and ``toolsCalling.length`` are truthy
    (``packages/agent-runtime/src/agents/GeneralChatAgent.ts``).
    Empty ``delta.tool_calls`` plus ``finish_reason=stop`` falls through to
    ``type: 'finish'``.
    """
    return len(view.tool_calls) > 0
