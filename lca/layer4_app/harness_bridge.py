"""Layer-4 factory that builds a LiveAgent for the harness registry."""

from __future__ import annotations

from typing import Any

from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore
from lca.layer0_infra.llm_resolver import ProductionLLMResolver
from lca.layer0_infra.tools.default_set import build_g2a_chat_tools
from lca.layer4_app.api import Agent
from lca.layer4_app.harness_live import CognitiveLiveAgent


def build_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    plugin_scope: Any | None,
) -> OwnerAgentHandle:
    """Build a LiveAgent with real LLM and tools.

    When plugin_scope is provided, the Agent will use it for capability resolution
    through AgentComposer.compose(scope=...). When not provided, falls back to
    ambient resolution (legacy path).

    LLM and tools are resolved from production defaults, not mock.
    """
    raw = options or {}

    # Resolve LLM: explicit > production resolver > mock (last resort)
    llm = raw.get("llm")
    if llm is None:
        try:
            resolver = ProductionLLMResolver()
            if resolver.is_available():
                llm = resolver.resolve(mode="solo")
            else:
                # Fallback to mock if no LLM credentials
                from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

                llm = MockLLMAdapter()
        except Exception:
            from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

            llm = MockLLMAdapter()

    # Resolve tools: explicit > ambient build
    tools = raw.get("tools")
    if tools is None:
        tools = build_g2a_chat_tools()

    agent = Agent(
        role=str(raw.get("role") or "agent"),
        goal=str(raw.get("goal") or ""),
        backstory=str(raw.get("backstory") or ""),
        tools=tuple(tools),
        llm=llm,
        max_steps=int(raw.get("max_steps") or 8),
        scope=plugin_scope,
    )
    live = CognitiveLiveAgent(agent, store, inbox, identity_id=identity_id)
    return OwnerAgentHandle(live)
