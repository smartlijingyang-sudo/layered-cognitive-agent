"""Layer-4 factory that builds a LiveAgent for the harness registry."""

from __future__ import annotations

from typing import Any

from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer4_app.api import Agent
from lca.layer4_app.harness_live import CognitiveLiveAgent


def build_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    plugin_scope: Any | None,
) -> OwnerAgentHandle:
    raw = options or {}
    llm = raw.get("llm") or MockLLMAdapter()
    agent = Agent(
        role=str(raw.get("role") or "agent"),
        goal=str(raw.get("goal") or ""),
        backstory=str(raw.get("backstory") or ""),
        tools=tuple(raw.get("tools") or ()),
        llm=llm,
        max_steps=int(raw.get("max_steps") or 8),
        scope=plugin_scope,
    )
    live = CognitiveLiveAgent(agent, store, inbox, identity_id=identity_id)
    return OwnerAgentHandle(live)
