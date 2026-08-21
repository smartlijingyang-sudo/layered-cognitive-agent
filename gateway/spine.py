"""Session spine handles: AgentRegistry + CommandGateway + projections.

The session spine is gateway infrastructure, not part of the harness
profile. It is constructed at ``create_app()`` time, but the cordis
ctx it hands to live agent builders is resolved **per call** from
``app.state.ctx`` — which is set by the lifespan after the harness
profile boots.

This decouples session spine construction from profile boot: the
spine is wired up eagerly so request handlers can find it on
``app.state``, but the ctx it provides comes from the boot-time
plugin tree when each session is created.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from lca.harness.agent.registry import AgentRegistry
from lca.harness.command.gateway import CommandGateway
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.projection.web import ActivityProjection, ConversationProjection
from lca.harness.skills import SkillsProjection
from lca.layer4_app.harness_bridge import build_live_agent


def bind_session_spine(
    *,
    sessions_dir: Path,
    ctx_provider: Callable[[], Any | None] | None = None,
    cordis_ctx: Any | None = None,
) -> tuple[AgentRegistry, CommandGateway, InMemoryProjectionRegistry]:
    """Bind the session spine with a lazy ctx provider.

    Args:
        sessions_dir: Where session JSONL files live.
        ctx_provider: Callable returning the booted cordis ctx. Called
            per session creation. If None, falls back to ``cordis_ctx``
            (deprecated) or None (library fallback path).
        cordis_ctx: Deprecated eager ctx — used only if ``ctx_provider``
            is None.

    Returns:
        ``(registry, command_gateway, projections)``. Bind them onto
        ``app.state`` and let request handlers use them.
    """
    projections = InMemoryProjectionRegistry()
    projections.register(ConversationProjection())
    projections.register(ActivityProjection())
    projections.register(SkillsProjection())
    registry = AgentRegistry(
        sessions_dir=sessions_dir,
        projections=projections,
        live_builder=build_live_agent,
        ctx_provider=ctx_provider,
        cordis_ctx=cordis_ctx,
    )
    gateway = CommandGateway(registry, projections)
    return registry, gateway, projections


def ctx_provider_from_app(app: Any) -> Callable[[], Any | None]:
    """Build a ctx_provider that reads ``app.state.ctx``.

    Use this when constructing the session spine: pass the returned
    callable to :func:`bind_session_spine`. The callable resolves
    ``app.state.ctx`` on each call, so it picks up the booted ctx
    after the lifespan runs without holding a stale reference.
    """

    def _provider() -> Any | None:
        return getattr(app.state, "ctx", None)

    return _provider
