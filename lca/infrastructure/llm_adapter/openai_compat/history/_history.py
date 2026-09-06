"""Project neutral tool history onto OpenAI / Anthropic request messages."""

from __future__ import annotations

import json
from typing import Any


def openai_messages_with_history(
    prompt: str, history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    for item in history:
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
            if openai_calls:
                messages.append({"role": "assistant", "content": None, "tool_calls": openai_calls})
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
    return messages


def anthropic_messages_with_history(
    prompt: str, history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    for item in history:
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
    return messages
