"""Process-wide session spine handles. Default unused (flag off)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.harness.agent.registry import AgentRegistry
from lca.harness.command.gateway import CommandGateway
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.projection.web import ActivityProjection, ConversationProjection
from lca.harness.skills import SkillsProjection
from lca.layer4_app.harness_bridge import build_live_agent

_registry: AgentRegistry | None = None
_gateway: CommandGateway | None = None
_projections: InMemoryProjectionRegistry | None = None


def bind_session_spine(
    *,
    sessions_dir: Path,
    cordis_ctx: Any | None = None,
) -> tuple[AgentRegistry, CommandGateway, InMemoryProjectionRegistry]:
    """Bind the session spine to disk persistence.

    `cordis_ctx` is the cordis.Context produced by boot_profile(); AgentRegistry
    uses it to resolve live agent builders, llm, tools, etc. via ctx.inject().
    Falls back to None (which AgentRegistry handles gracefully).
    """
    global _registry, _gateway, _projections
    projections = InMemoryProjectionRegistry()
    projections.register(ConversationProjection())
    projections.register(ActivityProjection())
    projections.register(SkillsProjection())
    registry = AgentRegistry(
        sessions_dir=sessions_dir,
        projections=projections,
        live_builder=build_live_agent,
        cordis_ctx=cordis_ctx,
    )
    gateway = CommandGateway(registry, projections)
    _registry = registry
    _gateway = gateway
    _projections = projections
    return registry, gateway, projections


def command_gateway() -> CommandGateway | None:
    return _gateway


def agent_registry() -> AgentRegistry | None:
    return _registry


def projections() -> InMemoryProjectionRegistry | None:
    return _projections
