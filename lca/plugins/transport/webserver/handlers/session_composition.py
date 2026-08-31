"""Composition of gateway-owned session infrastructure.

The application factory decides *that* session infrastructure is needed;
this module owns *how* the Session Spine is assembled. Chat streaming is
not this object's job — ``create_app`` wires the journal-backed run port
separately so the UI OpenAI SSE path cannot fall through to an empty stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.harness.state.projection import SessionProjectionRegistry
from lca.harness.agent.registry import AgentRegistry
from lca.harness.command.dispatcher import SessionCommandCarrier
from lca.plugins.transport.webserver.handlers import (
    bind_session_spine,
    ctx_provider_from_app,
    session_command_ledger_provider,
    session_live_builder_provider,
    session_persistence_factory_provider,
    session_projection_registry_factory_provider,
)


@dataclass(frozen=True)
class SessionComposition:
    """The gateway's Session Spine object graph (commands + projections)."""

    agent_registry: AgentRegistry
    command_gateway: SessionCommandCarrier
    projections: SessionProjectionRegistry


def compose_sessions(
    application: Any,
    *,
    sessions_dir: Path,
) -> SessionComposition:
    """Build the Session Spine used by ``/v1/sessions``.

    ``ctx_provider`` remains lazy: the Starlette lifespan owns profile boot and
    publishes ``app.state.ctx`` only after startup.
    """
    ctx_provider = ctx_provider_from_app(application)
    persistence_provider = session_persistence_factory_provider(ctx_provider)
    registry, command_gateway, projections = bind_session_spine(
        sessions_dir=sessions_dir,
        ctx_provider=ctx_provider,
        live_builder_provider=session_live_builder_provider(ctx_provider),
        persistence_factory_provider=persistence_provider,
        projection_registry_factory_provider=session_projection_registry_factory_provider(
            ctx_provider
        ),
        command_ledger_provider=session_command_ledger_provider(ctx_provider),
    )
    return SessionComposition(
        agent_registry=registry,
        command_gateway=command_gateway,
        projections=projections,
    )


__all__ = ["SessionComposition", "compose_sessions"]
