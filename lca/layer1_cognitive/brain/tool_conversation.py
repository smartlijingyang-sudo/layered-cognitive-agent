"""Prior tool turns as provider messages — LobeHub MessagesEngine parity.

LobeHub native keeps ``assistant.tool_calls`` + ``role=tool`` on the wire.
The model continues that protocol. Flattening tools into CONTEXT prose makes
the next completion invent text like ``[Tool calls]`` instead of calling.
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Observation, Turn
from lca.contracts.models.core.state import AgentState

_TOOL_RESULT_MAX = 32_000


def build_tool_history(state: AgentState) -> list[dict[str, Any]]:
    """Neutral history: assistant tool_calls + tool results, in turn order."""
    messages: list[dict[str, Any]] = []
    for index, turn in enumerate(state.history):
        if not isinstance(turn, Turn):
            continue
        if turn.decision.action_type != ActionType.USE_TOOL:
            continue
        if not turn.decision.tool_calls:
            continue
        tc = turn.decision.tool_calls[0]
        call_id = tc.call_id or f"history_{index}_{tc.tool_name}"
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call_id,
                        "name": tc.tool_name,
                        "arguments": tc.arguments,
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tc.tool_name,
                "content": _observation_content(turn.observation),
            }
        )
    return messages


def _observation_content(observation: Observation) -> str:
    """What the next completion should see — LobeHub tool message content, not journal JSON."""
    if not observation.success:
        return (observation.error or "tool failed").strip() or "tool failed"
    payload = observation.payload
    if payload is None:
        return ""
    if isinstance(payload, str):
        return _clip_tool_content(payload)
    if not isinstance(payload, dict):
        return _clip_tool_content(json.dumps(payload, ensure_ascii=False, default=str))
    for key in ("text", "summary", "output", "stdout", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _clip_tool_content(value)
    slim = {key: value for key, value in payload.items() if key != "state"}
    if not slim:
        return ""
    return _clip_tool_content(json.dumps(slim, ensure_ascii=False, default=str))


def _clip_tool_content(text: str) -> str:
    if len(text) > _TOOL_RESULT_MAX:
        return text[:_TOOL_RESULT_MAX] + "\n…(truncated)"
    return text
