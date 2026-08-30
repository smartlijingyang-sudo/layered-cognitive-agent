"""Durable session activation and live-handle ownership.

``SessionActivator`` is the only component that turns persisted Session facts
into a process-local live agent.  It deliberately owns the live cache, storage
construction, recovery, and disposal together, so command routing never needs
to know how a session is materialized.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import AgentHandle, LiveAgent, SessionLiveBuilder
from lca.contracts.harness.events import SessionCreated
from lca.contracts.harness.projection import SessionProjectionRegistry
from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.contracts.protocols.session_persistence import (
    SessionPersistence,
    SessionPersistenceFactory,
)
from lca.harness.session.inbox import Inbox
from lca.harness.session.recovery import recover_live_agent
from lca.harness.session.store import SessionStore


@dataclass
class LiveSession:
    """The process-local resources activated for one durable Session."""

    handle: AgentHandle
    store: SessionStore
    inbox: Inbox


class SessionActivator:
    """Own live-session materialization, recovery, and process-local disposal."""

    def __init__(
        self,
        *,
        sessions_dir: Path,
        projections: SessionProjectionRegistry,
        live_builder_provider: Callable[[], SessionLiveBuilder],
        ctx_provider: Callable[[], Any | None],
        persistence_factory_provider: Callable[[], SessionPersistenceFactory],
    ) -> None:
        self._sessions_dir = sessions_dir
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._projections = projections
        self._live_builder_provider = live_builder_provider
        self._ctx_provider = ctx_provider
        self._persistence_factory_provider = persistence_factory_provider
        self._live: dict[str, LiveSession] = {}

    def get(self, session_id: str) -> LiveAgent | None:
        """Return the currently activated agent, without forcing recovery."""
        entry = self._live.get(session_id)
        return entry.handle.agent if entry else None

    def entry_for(self, session_id: str) -> LiveSession | None:
        """Return the active resource bundle, without forcing recovery."""
        return self._live.get(session_id)

    def store_for(self, session_id: str) -> SessionStore | None:
        """Return the active SessionStore, without forcing recovery."""
        entry = self.entry_for(session_id)
        return entry.store if entry else None

    def active_agents(self) -> Iterable[LiveAgent]:
        """Expose a read-only iteration source for health projections."""
        return (entry.handle.agent for entry in self._live.values())

    async def create(
        self,
        profile: str,
        preset: str | None = None,
        *,
        session_id: str | None = None,
        parent_session: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AgentHandle:
        """Create a durable Session and activate its live owner exactly once."""
        sid = session_id or new_id("ses")
        existing = self._live.get(sid)
        if existing is not None:
            return existing.handle
        persistence = self._new_persistence(sid)
        persisted_header, _ = persistence.load()
        if persisted_header is not None:
            return self._resume_from_persistence(sid, persistence)
        header = SessionHeader(
            version=SESSION_FORMAT_VERSION,
            id=sid,
            created_at=int(time.time() * 1000),
            parent_session=parent_session,
            origin="user",
            agent_preset=preset,
            profile_digest=profile,
        )
        store = SessionStore(header, persistence=persistence)
        store.subscribe(self._projections.on_event)
        self._projections.bind_session(sid)
        inbox = Inbox(store)
        handle = self._live_builder_provider()(store, inbox, sid, options, self._ctx_provider())
        self._live[sid] = LiveSession(handle=handle, store=store, inbox=inbox)
        await store.append(SessionCreated(profile=profile, preset=preset), actor="system")
        return handle

    async def resume(self, session_id: str) -> AgentHandle:
        """Recover an absent live owner exclusively from durable Session facts."""
        existing = self._live.get(session_id)
        if existing is not None:
            return existing.handle
        return self._resume_from_persistence(session_id, self._new_persistence(session_id))

    def _resume_from_persistence(
        self,
        session_id: str,
        persistence: SessionPersistence,
    ) -> AgentHandle:
        """Materialize a missing live owner from one already selected durable backend."""
        store = SessionStore.load(persistence)
        store.subscribe(self._projections.on_event)
        self._projections.replay(session_id, list(store.events()))
        inbox = Inbox(store)
        handle = self._live_builder_provider()(store, inbox, session_id, None, self._ctx_provider())
        handle.agent.restore(recover_live_agent(store.events()))
        self._live[session_id] = LiveSession(handle=handle, store=store, inbox=inbox)
        return handle

    def store_or_load(self, session_id: str) -> SessionStore | None:
        """Read one Session's durable fact stream without activating a live agent.

        Command idempotency must inspect persisted facts before recovery: a
        duplicate command can be acknowledged from its completed receipt, and
        an uncertain partially settled command can be rejected without
        constructing a new loop owner.
        """

        existing = self.store_for(session_id)
        if existing is not None:
            return existing
        try:
            return SessionStore.load(self._new_persistence(session_id))
        except FileNotFoundError:
            return None

    async def entry_or_recover(self, session_id: str) -> LiveSession | None:
        """Return a live owner, recovering it only from the durable Session log."""
        entry = self.entry_for(session_id)
        if entry is not None:
            return entry
        try:
            handle = await self.resume(session_id)
        except FileNotFoundError:
            return None
        return self.entry_for(handle.agent.session_id)

    async def dispose(self, session_id: str, reason: str = "owner") -> None:
        """Release only process-local resources; durable facts remain intact."""
        entry = self._live.pop(session_id, None)
        if entry is not None:
            await entry.handle.dispose(reason)

    def _new_persistence(self, session_id: str) -> SessionPersistence:
        return self._persistence_factory_provider().create(
            session_id=session_id,
            sessions_dir=self._sessions_dir,
        )


__all__ = ["LiveSession", "SessionActivator"]
