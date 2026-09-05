"""Prior tool turns as provider messages — LobeHub MessagesEngine parity.

LobeHub native keeps ``assistant.tool_calls`` + ``role=tool`` on the wire.
The model continues that protocol. Flattening tools into CONTEXT prose makes
the next completion invent text like ``[Tool calls]`` instead of calling.
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.semantic_keys import OBS_TOOL_RESULTS
from lca.contracts.models.core.decision import Observation, Turn
from lca.contracts.models.core.state import AgentState

_TOOL_RESULT_MAX = 32_000


def build_tool_history(state: AgentState) -> list[dict[str, Any]]:
    """Neutral history: assistant tool_calls + tool results, in turn order.

    Parallel tool calls (one Decision → N tool_calls) are emitted as one
    assistant message with N tool_calls + N tool result messages — matching
    OpenAI / LobeHub native wire format.
    """
    messages: list[dict[str, Any]] = []
    for index, turn in enumerate(state.history):
        if not isinstance(turn, Turn):
            continue
        human_answer = _human_answer_message(turn)
        if human_answer is not None:
            messages.append(human_answer)
            continue
        if turn.decision.action_type != ActionType.USE_TOOL:
            continue
        if not turn.decision.tool_calls:
            continue

        # Build per-tool-call results: individual observations from parallel
        # execution (stored in extra[OBS_TOOL_RESULTS]), or the single
        # observation for legacy single-tool turns.
        tool_results = _tool_results_for_turn(turn)

        # One assistant message with all tool calls for this turn.
        assistant_calls = []
        for tc in turn.decision.tool_calls:
            call_id = tc.call_id or f"history_{index}_{tc.tool_name}"
            assistant_calls.append(
                {
                    "id": call_id,
                    "name": tc.tool_name,
                    "arguments": tc.arguments,
                }
            )
        messages.append({"role": "assistant", "tool_calls": assistant_calls})

        # One tool result message per tool call.
        for i, tc in enumerate(turn.decision.tool_calls):
            call_id = tc.call_id or f"history_{index}_{tc.tool_name}"
            obs = tool_results[i] if i < len(tool_results) else turn.observation
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": tc.tool_name,
                    "content": _observation_content(obs),
                }
            )
    return messages


def _human_answer_message(turn: Turn) -> dict[str, Any] | None:
    """Project resume answers onto the provider wire.

    ``askUserQuestion`` pauses before ``remember`` commits the USE_TOOL turn, so
    resume only folds an ``ASK_HUMAN`` turn. Without this branch the next LLM
    call sees empty history and asks the same questions again.
    """
    if turn.decision.action_type != ActionType.ASK_HUMAN:
        return None
    observation = turn.observation
    if observation is None or not observation.success:
        return None
    extra = observation.extra or {}
    if extra.get("source") != "human_answer":
        return None
    content = _observation_content(observation)
    if not content:
        return None
    return {"role": "user", "content": content}


def _tool_results_for_turn(turn: Turn) -> list[Observation]:
    """Extract per-tool-call observations from a turn.

    Parallel execution stores individual observations in
    ``observation.extra[OBS_TOOL_RESULTS]``.  Single-tool turns
    just wrap the turn observation in a list.
    """
    obs = turn.observation
    if obs is None:
        return []
    extra = obs.extra or {}
    results = extra.get(OBS_TOOL_RESULTS)
    if isinstance(results, list) and results:
        return [
            entry["observation"]
            for entry in results
            if isinstance(entry, dict) and isinstance(entry.get("observation"), Observation)
        ]
    return [obs]


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
    for key in ("text", "summary", "output", "stdout", "stderr", "content"):
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
