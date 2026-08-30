"""Public Session registry facade.

``AgentRegistry`` keeps the compatibility-facing API deliberately thin.  Durable
session activation lives in ``SessionActivator``; command semantics and
idempotency live in ``AgentCommandRouter``.  This leaves the registry with one
responsibility: exposing the Session Spine's live-agent boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from lca.contracts.harness.agent import AgentHandle, LiveAgent, SessionLiveBuilder
from lca.contracts.harness.command import CommandReceipt
from lca.contracts.harness.projection import SessionProjectionRegistry
from lca.contracts.protocols.session_command_ledger import SessionCommandLedger
from lca.contracts.protocols.session_persistence import SessionPersistenceFactory
from lca.harness.agent.activation import SessionActivator
from lca.harness.agent.command_router import AgentCommandRouter
from lca.harness.agent.health import live_totals as project_live_totals
from lca.harness.agent.health import status_counts as project_status_counts
from lca.harness.session.store import SessionStore


class AgentRegistry:
    """Expose one live agent per durable session through a stable façade."""

    def __init__(
        self,
        *,
        sessions_dir: Path,
        projections: SessionProjectionRegistry,
        live_builder_provider: Callable[[], SessionLiveBuilder],
        ctx_provider: Callable[[], Any | None],
        command_ledger_provider: Callable[[], SessionCommandLedger],
        persistence_factory_provider: Callable[[], SessionPersistenceFactory] | None = None,
    ) -> None:
        self._activator = SessionActivator(
            sessions_dir=sessions_dir,
            projections=projections,
            live_builder_provider=live_builder_provider,
            ctx_provider=ctx_provider,
            persistence_factory_provider=persistence_factory_provider,
        )
        self._commands = AgentCommandRouter(
            self._activator,
            command_ledger_provider=command_ledger_provider,
        )

    def get(self, session_id: str) -> LiveAgent | None:
        """Return an already active agent without initiating recovery."""
        return self._activator.get(session_id)

    def store_for(self, session_id: str) -> SessionStore | None:
        """Return an already active session store without initiating recovery."""
        return self._activator.store_for(session_id)

    def status_counts(self) -> dict[str, int]:
        """Project live-agent states into the stable health summary."""
        return project_status_counts(agent.status for agent in self._activator.active_agents())

    def live_totals(self) -> dict[str, int]:
        """Return Session Spine-compatible live-tail totals."""
        return project_live_totals()

    async def create(
        self,
        profile: str,
        preset: str | None = None,
        *,
        session_id: str | None = None,
        parent_session: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AgentHandle:
        """Create and activate a durable Session."""
        return await self._activator.create(
            profile,
            preset,
            session_id=session_id,
            parent_session=parent_session,
            options=options,
        )

    async def resume(self, session_id: str) -> AgentHandle:
        """Recover an absent live owner solely from durable Session facts."""
        return await self._activator.resume(session_id)

    async def dispose(self, session_id: str, reason: str = "owner") -> None:
        """Release process-local resources while retaining durable facts."""
        await self._activator.dispose(session_id, reason)

    async def create_session(
        self,
        *,
        idempotency_key: str,
        profile: str,
        preset: str | None,
        options: dict[str, Any] | None,
        session_id: str | None = None,
    ) -> CommandReceipt:
        """Create a session through the command-semantics boundary."""
        return await self._commands.create_session(
            idempotency_key=idempotency_key,
            profile=profile,
            preset=preset,
            options=options,
            session_id=session_id,
        )

    async def dispatch_message(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        content: str,
        role: str,
        message_id: str | None = None,
    ) -> CommandReceipt:
        """Dispatch an idempotent user message to a durable Session."""
        return await self._commands.dispatch_message(
            session_id=session_id,
            idempotency_key=idempotency_key,
            content=content,
            role=role,
            message_id=message_id,
        )

    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt:
        """Cancel an active or recoverable Session."""
        return await self._commands.cancel(session_id=session_id, keep_inbox=keep_inbox)

    async def resume_approval(
        self,
        *,
        session_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> CommandReceipt:
        """Resolve an idempotent approval command."""
        return await self._commands.resume_approval(
            session_id=session_id,
            approval_id=approval_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    async def steer(self, *, session_id: str, content: str) -> CommandReceipt:
        """Send a steering message to an active or recoverable Session."""
        return await self._commands.steer(session_id=session_id, content=content)

    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt:
        """Inject external context into an active or recoverable Session."""
        return await self._commands.inject(
            session_id=session_id,
            source=source,
            content=content,
        )
