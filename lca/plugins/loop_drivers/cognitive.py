"""Cognitive loop plugin — provides the legacy ``agent_loop`` capability and
registers the cognitive ``RunLoopDriver`` into the runtime registry.

ADR-0062 §6 — Driver boundary. The driver implementation lives in
``gateway.runs.loop_drivers.CognitiveRunDriver`` because it binds gateway
protocol types (RunSession, SOLO_MODE_KEY). This plugin stays free of
``gateway`` imports at module load time and resolves the driver through
a zero-arg factory — registration is identical to every other loop plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.harness.session.inbox import Inbox
    from lca.harness.session.store import SessionStore

_log = structlog.get_logger(__name__)


def build_cognitive_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Any | None,
) -> object:
    """Build a LiveAgent backed by the LCA cognitive loop."""
    opts = options or {}
    llm = opts.get("llm")
    if llm is None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

        llm = MockLLMAdapter()
    tools = opts.get("tools") or ()
    scope = cordis_ctx
    if scope is None:
        scope = opts.get("scope")
    if scope is None:
        from lca.layer4_app.api import get_or_create_default_ctx

        scope = get_or_create_default_ctx()
    from lca.harness.agent.handle import OwnerAgentHandle
    from lca.layer4_app.api import Agent

    agent = Agent(
        role=opts.get("role", identity_id),
        goal="",
        backstory="",
        tools=tuple(tools),
        llm=llm,
        scope=scope,
    )
    from lca.layer4_app.harness_live import CognitiveLiveAgent

    live = CognitiveLiveAgent(agent=agent, store=store, inbox=inbox, identity_id=identity_id)
    return OwnerAgentHandle(live)


def _cognitive_driver_factory() -> Any:
    """Lazy factory — keeps ``gateway`` imports out of plugin module load."""
    from gateway.runs.loop_drivers import CognitiveRunDriver

    return CognitiveRunDriver()


@plugin(
    id="lca-loop-cognitive",
    requires=["run_loop_driver_registry"],
    provides=["agent_loop", "run_loop_driver_registry[cognitive]"],
    implements=[],
    layer="L1",
    effects="none",
    description=(
        "Provide the legacy agent_loop factory and register the cognitive "
        "RunLoopDriver. The bundle decides whether alternative loop plugins "
        "are loaded alongside the cognitive one."
    ),
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: dict[str, Any]) -> None:
    target = (config or {}).get("target", "cognitive") if isinstance(config, dict) else "cognitive"
    registry = ctx.inject("run_loop_driver_registry")
    registry.register(target, _cognitive_driver_factory)
    ctx.provide("agent_loop", build_cognitive_live_agent)
    _log.debug("agent_loop_registered", target=target)
