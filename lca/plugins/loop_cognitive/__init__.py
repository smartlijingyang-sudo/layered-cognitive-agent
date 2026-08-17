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
    from lca.layer4_app.api import Agent
    from lca.layer4_app.harness_live import CognitiveLiveAgent

    raw = options or {}

    # Resolve LLM: explicit option wins, else the plugin scope's ``llm``
    # seam (Definition provider), else a bare mock.
    llm = raw.get("llm")
    if llm is None:
        llm = _resolve_llm_from_scope(plugin_scope, raw)
    if llm is None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

        llm = MockLLMAdapter()

    # Resolve tools: explicit option wins, else the plugin scope's ``tools``
    # seam (factory registry forked for this run), else the legacy builder.
    tools = raw.get("tools")
    if tools is None:
        tools = _resolve_tools_from_scope(plugin_scope, raw)

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


def _resolve_llm_from_scope(plugin_scope: Any, raw: dict[str, Any]) -> Any:
    """Resolve the current LLM provider from the plugin scope's ``llm`` seam.

    Prefers an explicit provider name in options (e.g. ``{"provider": "real"}``),
    then the scope's active provider, then a per-run resolver fallback.
    """
    from lca.layer0_infra.llm_resolver import ProductionLLMResolver

    provider_name = raw.get("provider")
    if plugin_scope is not None:
        try:
            llm_svc = plugin_scope.resolve("llm")
            if provider_name:
                try:
                    return llm_svc.providers.get(provider_name)
                except KeyError:
                    pass
            try:
                return llm_svc.providers.current()
            except RuntimeError:
                pass
        except Exception:
            _log.debug("llm_scope_resolve_fallback", exc_info=True)
    try:
        resolver = ProductionLLMResolver()
        if resolver.is_available():
            return resolver.resolve(mode="solo")
    except Exception:
        _log.debug("llm_resolver_fallback", exc_info=True)
        return None
    return None


def _resolve_tools_from_scope(plugin_scope: Any, raw: dict[str, Any]) -> Any:
    """Resolve the tool set from the plugin scope's ``tools`` seam.

    Prefers an explicit tool list in options, then forks the scope's tool
    factory registry for this run, then falls back to the legacy builder.
    """
    from lca.layer0_infra.tools.default_set import build_g2a_chat_tools

    if plugin_scope is not None:
        try:
            tools_svc = plugin_scope.resolve("tools")
            run = type(
                "_Run", (), {"plane": raw.get("bindings"), "bindings": raw.get("bindings")}
            )()
            forked = tools_svc.fork_for_run(run)
            tools = forked.list_tools()
            if tools:
                return tools
        except Exception:
            _log.debug("tools_scope_resolve_fallback", exc_info=True)
    return build_g2a_chat_tools()


def apply(ctx: Any, config: Any) -> None:
    """Register the cognitive loop builder at the ``agent_loop`` seam."""
    ctx.mount("agent_loop", build_cognitive_live_agent)
    _log.debug("cognitive_loop_registered", seam_key="agent_loop")
