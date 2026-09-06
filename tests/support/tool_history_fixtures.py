"""Test-only AgentState.history → provider wire helper (legacy shape checks)."""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.semantic.semantic_keys import OBS_TOOL_RESULTS
from lca.contracts.models.core.execution.decision import Observation, Turn
from lca.contracts.models.core.state.state import AgentState

_TOOL_RESULT_MAX = 32_000


def build_tool_history(state: AgentState) -> list[dict[str, Any]]:
    """Build neutral tool wire from in-process control turns (tests only)."""
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
        tool_results = _tool_results_for_turn(turn)
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
