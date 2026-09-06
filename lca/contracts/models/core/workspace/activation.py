"""Activation contract — skill activated during an agent run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivatedSkill:
    """A skill that has been activated into the agent's context.

    ``activated_at_step`` is 0 when created by L0 (contextvar scope);
    L2 runtime fills the real step number when syncing to AgentState.
    """

    skill_id: str
    name: str
    activated_at_step: int = 0
