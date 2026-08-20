"""CognitiveLoopFactory plugin — Tier-3 (loop driver).

The production cognitive loop is constructed by ``spawn_agent`` and
never goes through this factory; this fallback exists for the legacy
path that resolves the loop from cordis context (see
``lca.layer4_app.harness_bridge.build_live_agent``).
"""

from __future__ import annotations
from typing import Any
import structlog
from lca.harness.plugin_api import plugin, PluginKind

_log = structlog.get_logger(__name__)


def build_cognitive_live_agent(
    store: object,
    inbox: object,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Any | None,
) -> object:
    """Build a LiveAgent backed by the LCA cognitive loop.

    Wires ``CognitiveLiveAgent`` around an ``Agent`` constructed from
    the harness-provided ``options`` (llm + tools).  When options are
    absent (the resume path) we fall back to a ``MockLLMAdapter`` so
    the harness can reconstruct a working LiveAgent purely from
    persisted journal state — production wiring should still go
    through ``spawn_agent()``.
    """
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
    requires=["run_loop_driver_registry"],
    provides=["agent_loop", "run_loop_driver_registry[cognitive]"],
    implements=[],
    layer="L1",
    effects="none",
    description="Register the cognitive loop driver at run_loop_driver_registry[cognitive].",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: Any, config: Any) -> None:
    """Register the cognitive loop at two seams:

    - ``agent_loop`` → consumed by the legacy session-spine path
      (``harness_bridge.build_live_agent`` → ``AgentRegistry``).
    - ``run_loop_driver_registry["cognitive"]`` → consumed by
      ``gateway/runs/execute.py:execute_run`` for the ``/runs`` HTTP path.
    """
    ctx.provide("agent_loop", build_cognitive_live_agent)
    from gateway.runs.loop_drivers import CognitiveRunDriver

    target = "cognitive"
    if isinstance(config, dict) and isinstance(config.get("target"), str):
        target = config["target"]
    ctx.inject("run_loop_driver_registry").register(target, CognitiveRunDriver())
    _log.debug("cognitive_loop_registered", seam_key="agent_loop", driver_target=target)
