"""LLM output stream channel classification (ADR-0051 Phase 2)."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType, StreamChannel

_TERMINAL_ACTIONS = frozenset(
    {
        ActionType.RESPOND.value,
        ActionType.STOP.value,
        ActionType.ASK_HUMAN.value,
    }
)


def classify_output_channel(accumulated: str) -> str:
    """Classify streamed LLM text as decision draft vs user-facing answer."""
    text = accumulated.lstrip()
    if not text:
        return StreamChannel.DECISION.value

    if '"action_type"' in text:
        for action in _TERMINAL_ACTIONS:
            if f'"{action}"' in text:
                return StreamChannel.ANSWER.value
        return StreamChannel.DECISION.value

    if text.startswith(("{", "```", "<")):
        return StreamChannel.DECISION.value

    return StreamChannel.ANSWER.value
