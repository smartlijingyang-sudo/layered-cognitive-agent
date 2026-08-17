"""CognitiveLoopFactory plugin — wraps the LCA cognitive loop as a pluggable agent loop.

When loaded via profile YAML, this plugin registers itself at the ``agent_loop``
seam key.  ``build_live_agent()`` resolves this seam to obtain the builder,
making the loop fully swappable through YAML configuration.

Swap to a different loop by replacing this plugin in the profile::

    patch:
      - remove: lca.loop.cognitive
      - insert:
          id: lca.loop.dsh_bridge
          name: lca.plugins.loop_dsh_bridge
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.contracts.harness.plugin import PluginKind, PluginManifest

_log = structlog.get_logger(__name__)

manifest = PluginManifest(
    id="lca.loop.cognitive",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("agent_loop",),
)

name = "lca.loop.cognitive"


def build_cognitive_live_agent(
    store: Any,
    inbox: Any,
    identity_id: str,
    options: dict[str, Any] | None,
    plugin_scope: Any | None,
) -> Any:
    """Build a LiveAgent backed by the LCA cognitive loop (Agent + CognitiveRuntime).

    This is the default loop builder.  It resolves a real LLM and tools,
    creates an ``Agent`` (whose ``__init__`` triggers ``AgentComposer.compose()``
    → ``CognitiveRuntime``), and wraps it in a ``CognitiveLiveAgent``.

    The function signature matches the ``LiveAgentBuilder`` protocol expected
    by ``AgentRegistry``.
    """
    from lca.harness.agent.handle import OwnerAgentHandle
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver
    from lca.layer0_infra.tools.default_set import build_g2a_chat_tools
    from lca.layer4_app.api import Agent
    from lca.layer4_app.harness_live import CognitiveLiveAgent

    raw = options or {}

    # Resolve LLM
    llm = raw.get("llm")
    if llm is None:
        try:
            resolver = ProductionLLMResolver()
            if resolver.is_available():
                llm = resolver.resolve(mode="solo")
            else:
                from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

                llm = MockLLMAdapter()
        except Exception:
            from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

            llm = MockLLMAdapter()

    # Resolve tools
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


def apply(ctx: Any, config: Any) -> None:
    """Register the cognitive loop builder at the ``agent_loop`` seam."""
    ctx.mount("agent_loop", build_cognitive_live_agent)
    _log.debug("cognitive_loop_registered", seam_key="agent_loop")
