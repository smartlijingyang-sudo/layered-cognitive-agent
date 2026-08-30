"""Carrier input types for legacy run session setup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gateway.modes import DEFAULT_MODE
from gateway.runs.identity import AgentRef
from lca.contracts.models.core.conversation import ConversationTurn


@dataclass(frozen=True)
class RunSessionRequest:
    """Carrier input required to create one legacy ``RunSession``."""

    question: str
    user_text: str
    mode: str = DEFAULT_MODE
    attachment_ids: Sequence[str] = ()
    prior_turns: Sequence[ConversationTurn] = ()
    agent: AgentRef | None = None
    device_id: str = ""
    plane: str = ""
    extra_plane: str = ""
    execution_target: str = ""


__all__ = ["RunSessionRequest"]
