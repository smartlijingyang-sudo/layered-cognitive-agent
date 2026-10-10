"""Project neutral tool history onto OpenAI / Anthropic request messages.

Spec §G: system prompt goes to ``role=system`` (the first message on
both OpenAI Chat Completions and Anthropic Messages wire shapes); it is
never injected as ``role=user``.
"""

from __future__ import annotations

import json
from typing import Any


def openai_messages_with_history(
    system: str | None,
    prompt: str,
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """OpenAI-compatible messages with optional ``role=system`` header.

    ``system`` (when truthy) becomes the first message with ``role=system``.
    ``history`` items follow; ``prompt`` becomes the final user turn only
    when it carries text — a caller whose message list is already complete
    passes an empty prompt, and appending an empty user turn would leave a
    trailing ``role=tool`` row stripped of its ``tool_call_id``.
    """
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    for item in history or ():
        role = item.get("role")
        if role == "assistant":
            calls = item.get("tool_calls") or []
            openai_calls = []
            for call in calls:
                if not isinstance(call, dict):
                    continue
                arguments = call.get("arguments", {})
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {}, ensure_ascii=False)
                openai_calls.append(
                    {
                        "id": str(call.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(call.get("name") or ""),
                            "arguments": arguments,
                        },
                    }
                )
            text = item.get("content")
            text = text if isinstance(text, str) and text.strip() else None
            if openai_calls:
                messages.append({"role": "assistant", "content": text, "tool_calls": openai_calls})
            elif text is not None:
                messages.append({"role": "assistant", "content": text})
        elif role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(item.get("tool_call_id") or ""),
                    "content": str(item.get("content") or ""),
                }
            )
        elif role == "user":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                messages.append({"role": "user", "content": content})
    if prompt and prompt.strip():
        messages.append({"role": "user", "content": prompt})
    return _sanitize_hanging_tool_calls(messages)


def _sanitize_hanging_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce OpenAI wire protocol on the final message sequence.

    Any assistant message that has `tool_calls` must be followed by `role='tool'`
    messages for each declared `id` before a user message, before another
    tool-calling assistant message, or before the end of the message list.
    """
    if not messages:
        return messages

    sanitized: list[dict[str, Any]] = []
    i = 0
    n = len(messages)

    while i < n:
        msg = messages[i]
        sanitized.append(msg)
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected_ids = [
                c.get("id") for c in msg["tool_calls"] if isinstance(c, dict) and c.get("id")
            ]
            if expected_ids:
                j = i + 1
                answered_ids = set()
                while j < n and messages[j].get("role") == "tool":
                    sanitized.append(messages[j])
                    t_id = messages[j].get("tool_call_id")
                    if t_id:
                        answered_ids.add(t_id)
                    j += 1

                missing_ids = [exp_id for exp_id in expected_ids if exp_id not in answered_ids]
                # Enforce closure if followed by user, another tool-calling assistant, or end of list
                should_close = False
                if (
                    j >= n
                    or messages[j].get("role") == "user"
                    or (messages[j].get("role") == "assistant" and messages[j].get("tool_calls"))
                ):
                    should_close = True

                if should_close and missing_ids:
                    for exp_id in missing_ids:
                        sanitized.append(
                            {
                                "role": "tool",
                                "tool_call_id": exp_id,
                                "content": "[system: tool execution not completed in session]",
                            }
                        )
                i = j - 1
        i += 1

    return sanitized


def anthropic_messages_with_history(
    system: str | None,
    prompt: str,
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Anthropic-compatible messages with optional in-band ``role=system`` header.

    Anthropic's native wire shape uses a top-level ``system`` field, but it
    also accepts ``role=system`` as the first in-messages entry. Keeping a
    single wire path with OpenAI: ``system`` lives in messages[0] when set.
    """
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    for item in history or ():
        role = item.get("role")
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            for call in item.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                arguments = call.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(call.get("name") or ""),
                        "input": arguments,
                    }
                )
            text = item.get("content")
            if isinstance(text, str) and text.strip():
                blocks.insert(0, {"type": "text", "text": text})
            if blocks:
                messages.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(item.get("tool_call_id") or ""),
                            "content": str(item.get("content") or ""),
                        }
                    ],
                }
            )
        elif role == "user":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                messages.append({"role": "user", "content": content})
    if prompt and prompt.strip():
        messages.append({"role": "user", "content": prompt})
    return messages
