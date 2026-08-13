"""Recover native tool_calls when a model writes them as visible prose.

LobeHub only executes ``assistant.tool_calls``. Some completions (Qwen / thinking
leaks) emit ``[Tool call: name]\\n{json}`` as text. That is not a user answer.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.llm import NativeToolCall

_LEAKED_CALL = re.compile(
    r"\[Tool call:\s*([A-Za-z_][\w]*)\]\s*(\{.*\})\s*\Z",
    re.DOTALL,
)
_TOOL_NAME = re.compile(r"^[A-Za-z_][\w]{0,63}$")


def recover_leaked_tool_calls(text: str) -> tuple[str, list[NativeToolCall]]:
    """Split leftover prose from trailing leaked tool-call markup.

    Returns ``(visible_text, tool_calls)``. ``visible_text`` never includes the
    protocol junk. Empty tool_calls means the text was a real answer.
    """
    raw = (text or "").strip()
    if not raw:
        return "", []
    match = _LEAKED_CALL.search(raw)
    if match is None:
        return raw, []
    name = match.group(1)
    if not _TOOL_NAME.match(name):
        return raw, []
    try:
        arguments = json.loads(match.group(2))
    except json.JSONDecodeError:
        return raw, []
    if not isinstance(arguments, dict):
        return raw, []
    cleaned = raw[: match.start()].rstrip()
    return cleaned, [
        NativeToolCall(call_id=new_id("call"), name=name, arguments=_string_keys(arguments))
    ]


def _string_keys(arguments: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in arguments.items()}
