"""Carrier input types for legacy run session setup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.team.modes_catalog import DEFAULT_MODE
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.plugins.transport.webserver.read.runs.identity.identity import AgentRef


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
    user_id: str = ""
    """ADR-0252: 调用者用户身份（来自 x-lca-user-id 头）。"""
    topic_id: str = ""
    """本 run 所属会话。在 dispatch 之前落到 session，见 ``RunRequest.topic_id``。"""
    origin: str = "user"
    """ADR-0268 §4：``handoff`` 轮才把 ``lca.nothing_to_do`` 放上 wire。"""


__all__ = ["RunSessionRequest"]
