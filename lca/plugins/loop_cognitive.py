"""Cognitive loop factory plugin — provides the legacy ``agent_loop`` capability.

ADR-0062 §6 — Driver boundary. The cognitive driver
(:class:`gateway.runs.loop_drivers.CognitiveRunDriver`) lives in the
gateway because it binds gateway protocol types (RunSession,
PlaneBindings, SOLO_MODE_KEY) to the LCA runtime. This plugin must NOT
import from ``gateway``; it only exposes the legacy ``agent_loop``
factory used by ``harness_bridge.build_live_agent``.

The actual driver registration into the runtime registry happens from
``gateway/app.py`` after the plugin tree is booted (see
:func:`gateway.runs.loop_drivers.register_default_drivers`).
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.harness.plugin_api import PluginKind, plugin

_log = structlog.get_logger(__name__)


def build_cognitive_live_agent(
    store: object,
    inbox: object,
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
        goal=opts.get("goal", ""),
        backstory=opts.get("backstory", ""),
        tools=tuple(tools),
        llm=llm,
        scope=scope,
    )
    from lca.layer4_app.harness_live import CognitiveLiveAgent

    live = CognitiveLiveAgent(agent=agent, store=store, inbox=inbox, identity_id=identity_id)
    return OwnerAgentHandle(live)


@plugin(
    id="lca-loop-cognitive",
    requires=[],
    provides=["agent_loop"],
    implements=[],
    layer="L1",
    effects="none",
    description=(
        "Provide the legacy agent_loop factory used by "
        "harness_bridge.build_live_agent. Cognitive driver registration "
        "into the runtime registry is performed by the gateway at boot time "
        "(see gateway.runs.loop_drivers.register_default_drivers)."
    ),
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: Any, config: Any) -> None:
    """Expose ``agent_loop`` only.

    Driver registration was removed (ADR-0062 §6): the gateway owns its
    own driver implementations and registers them against the runtime
    registry after the LCA plugin tree finishes booting.
    """
    ctx.provide("agent_loop", build_cognitive_live_agent)
    _log.debug("agent_loop_registered")
