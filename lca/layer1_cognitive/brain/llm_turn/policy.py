"""Resolve LlmTurnMode from AgentState (LobeHub phase hints)."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.state import AgentState
from lca.layer0_infra.search.constants import WEB_SEARCH_TOOL
from lca.layer0_infra.search.router import resolve_llm_search_kwargs
from lca.layer1_cognitive.brain.llm_turn.mode import LlmTurnMode

_POST_SEARCH_TOOL_CHOICE = "none"


def resolve_llm_turn_mode(state: AgentState) -> LlmTurnMode:
    """Pick stream vs summarize-only for this step."""
    if _last_turn_was_successful_web_search(state):
        return LlmTurnMode.SUMMARIZE
    return LlmTurnMode.STREAM


def build_llm_call_kwargs(*, state: AgentState, task: str) -> dict[str, object]:
    """Provider kwargs: search fallback + post-search summarize guard."""
    kwargs: dict[str, object] = dict(resolve_llm_search_kwargs(task=task))
    if resolve_llm_turn_mode(state) == LlmTurnMode.SUMMARIZE:
        kwargs["tool_choice"] = _POST_SEARCH_TOOL_CHOICE
    return kwargs


def _last_turn_was_successful_web_search(state: AgentState) -> bool:
    if not state.history:
        return False
    turn = state.history[-1]
    if turn.decision.action_type != ActionType.USE_TOOL or not turn.decision.tool_calls:
        return False
    if turn.decision.tool_calls[0].tool_name != WEB_SEARCH_TOOL:
        return False
    return bool(turn.observation.success)
