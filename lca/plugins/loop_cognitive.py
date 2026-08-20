"""CognitiveLoopFactory plugin — Tier-3 (loop driver).

The production cognitive loop is constructed directly by
`AgentComposer.compose` and never goes through this factory; this
fallback exists for the legacy path that resolves the loop from
cordis context (see ``lca.layer4_app.harness_bridge.build_live_agent``).
Per the cognitive-primitive constitution v3 the plugin does not drive
``CognitiveRuntime._loop``; calling it should surface a clear error
instead of silently returning a placeholder.
"""

from __future__ import annotations

from typing import Any

import structlog
from cordis import Context, plugin

from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore
from lca.layer4_app.api import Agent

_log = structlog.get_logger(__name__)


def build_cognitive_live_agent(
    store: SessionStore,
    inbox: Inbox,
    identity_id: str,
    options: dict[str, Any] | None,
    cordis_ctx: Any | None,
) -> OwnerAgentHandle:
    """Build a LiveAgent backed by the LCA cognitive loop.

    Wires ``CognitiveLiveAgent`` around an ``Agent`` constructed from
    the harness-provided ``options`` (llm + tools).  When options are
    absent (the resume path) we fall back to a ``MockLLMAdapter`` so
    the harness can reconstruct a working LiveAgent purely from
    persisted journal state — production wiring should still go
    through ``AgentComposer.compose()``.
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
        # No cordis ctx supplied — fall back to the cached default.
        from lca.layer4_app.api import get_or_create_default_ctx

        scope = get_or_create_default_ctx()
    agent = Agent(
        role=opts.get("role", identity_id),
        goal=opts.get("goal", ""),
        backstory=opts.get("backstory", ""),
        tools=tuple(tools),
        llm=llm,
        scope=scope,
    )
    from lca.layer4_app.harness_live import CognitiveLiveAgent

    live = CognitiveLiveAgent(
        agent=agent,
        store=store,
        inbox=inbox,
        identity_id=identity_id,
    )
    return OwnerAgentHandle(live)


@plugin(name="lca-loop-cognitive", inject=["run_loop_driver_registry"])
async def setup(ctx: Context, config: Any) -> None:
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
