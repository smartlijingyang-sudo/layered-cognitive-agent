"""Carrier input types for legacy run session setup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.team.modes_catalog import DEFAULT_MODE
from lca.contracts.models.core.conversation import ConversationTurn
from lca.plugins.transport.webserver.handlers.runs.observability.identity import AgentRef


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
    assistant_id: str = ""
    """ADR-0187 §3 D7 一次性 run 绑定（``asst_*``）；空 = 遗留默认 agent。"""


__all__ = ["RunSessionRequest"]
