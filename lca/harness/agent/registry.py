"""AgentRegistry — transactional create/resume/dispose (spec §3.3)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import LiveAgent
from lca.contracts.harness.command import CommandReceipt
from lca.contracts.harness.events import CommandRejected, SessionCreated
from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.session.inbox import Inbox
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore

LiveBuilder = Callable[
    [SessionStore, Inbox, str, dict[str, Any] | None, Any],
    OwnerAgentHandle,
]


@dataclass
class _AgentEntry:
    handle: OwnerAgentHandle
    store: SessionStore
    inbox: Inbox


class AgentRegistry:
    """One live agent per session_id. Implements AgentRegistryFacade."""

    def __init__(
        self,
        *,
        sessions_dir: Path,
        projections: InMemoryProjectionRegistry,
        live_builder: LiveBuilder,
        cordis_ctx: Any | None = None,
        plugin_scope: Any | None = None,  # DEPRECATED: use cordis_ctx
    ) -> None:
        self._sessions_dir = sessions_dir
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._projections = projections
        self._live_builder = live_builder
        # Prefer cordis_ctx; fall back to deprecated plugin_scope for back-compat.
        self._cordis_ctx = cordis_ctx if cordis_ctx is not None else plugin_scope
        self._live: dict[str, _AgentEntry] = {}
        self._idempotency: dict[str, CommandReceipt] = {}

    def get(self, session_id: str) -> LiveAgent | None:
        entry = self._live.get(session_id)
        return entry.handle.agent if entry else None

    def store_for(self, session_id: str) -> SessionStore | None:
        entry = self._live.get(session_id)
        return entry.store if entry else None

    async def create(
        self,
        profile: str,
        preset: str | None = None,
        *,
        session_id: str | None = None,
        parent_session: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> OwnerAgentHandle:
        sid = session_id or new_id("ses")
        if sid in self._live:
            return self._live[sid].handle
        header = SessionHeader(
            version=SESSION_FORMAT_VERSION,
            id=sid,
            created_at=int(time.time() * 1000),
            parent_session=parent_session,
            origin="user",
            agent_preset=preset,
            profile_digest=profile,
        )
        persistence = JsonlSessionPersistence(self._sessions_dir / f"{sid}.jsonl")
        store = SessionStore(header, persistence=persistence)
        store.subscribe(self._projections.on_event)
        self._projections.bind_session(sid)
        inbox = Inbox(store)
        handle = self._live_builder(store, inbox, sid, options, self._cordis_ctx)
        self._live[sid] = _AgentEntry(handle=handle, store=store, inbox=inbox)
        await store.append(SessionCreated(profile=profile, preset=preset), actor="system")
        return handle

    async def resume(self, session_id: str) -> OwnerAgentHandle:
        existing = self._live.get(session_id)
        if existing is not None:
            return existing.handle
        persistence = JsonlSessionPersistence(self._sessions_dir / f"{session_id}.jsonl")
        store = SessionStore.load(persistence)
        store.subscribe(self._projections.on_event)
        self._projections.replay(session_id, list(store.events()))
        inbox = Inbox(store)
        handle = self._live_builder(store, inbox, session_id, None, self._cordis_ctx)
        status = self._status_from_store(store)
        agent = handle.agent
        if hasattr(agent, "_status"):
            agent._status = status
        self._live[session_id] = _AgentEntry(handle=handle, store=store, inbox=inbox)
        return handle

    async def dispose(self, session_id: str, reason: str = "owner") -> None:
        entry = self._live.pop(session_id, None)
        if entry is not None:
            await entry.handle.dispose(reason)

    async def create_session(
        self,
        *,
        idempotency_key: str,
        profile: str,
        preset: str | None,
        options: dict | None,
    ) -> CommandReceipt:
        cached = self._idempotency.get(idempotency_key)
        if cached is not None:
            return cached
        handle = await self.create(profile, preset, options=options)
        receipt = CommandReceipt(
            command_id=idempotency_key,
            session_id=handle.agent.session_id,
            seq=self._live[handle.agent.session_id].store.current_seq,
            accepted=True,
        )
        self._idempotency[idempotency_key] = receipt
        return receipt

    async def dispatch_message(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        content: str,
        role: str,
    ) -> CommandReceipt:
        cached = self._idempotency.get(idempotency_key)
        if cached is not None:
            return cached
        entry = self._live.get(session_id)
        if entry is None:
            return await self._reject(session_id, idempotency_key, "unknown session")
        from lca.contracts.harness.agent import UserMessage

        receipt_msg = await entry.handle.agent.followup(UserMessage(content=content, role=role))
        receipt = CommandReceipt(
            command_id=idempotency_key,
            session_id=session_id,
            seq=receipt_msg.seq,
            accepted=True,
        )
        self._idempotency[idempotency_key] = receipt
        return receipt

    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt:
        entry = self._live.get(session_id)
        if entry is None:
            return await self._reject(session_id, new_id("cmd"), "unknown session")
        entry.handle.agent.cancel(keep_inbox=keep_inbox)
        return CommandReceipt(
            command_id=new_id("cmd"),
            session_id=session_id,
            seq=entry.store.current_seq,
            accepted=True,
        )

    async def answer(self, *, session_id: str, answer: str) -> CommandReceipt:
        entry = self._live.get(session_id)
        if entry is None:
            handle = await self.resume(session_id)
            entry = self._live[handle.agent.session_id]
        answer_fn = getattr(entry.handle.agent, "answer", None)
        if callable(answer_fn):
            receipt_msg = await answer_fn(answer)
        else:
            from lca.contracts.harness.agent import UserMessage

            receipt_msg = await entry.handle.agent.followup(UserMessage(content=answer))
        return CommandReceipt(
            command_id=new_id("cmd"),
            session_id=session_id,
            seq=receipt_msg.seq,
            accepted=True,
        )

    async def steer(self, *, session_id: str, content: str) -> CommandReceipt:
        entry = self._live.get(session_id)
        if entry is None:
            return await self._reject(session_id, new_id("cmd"), "unknown session")
        from lca.contracts.harness.agent import UserMessage

        receipt_msg = await entry.handle.agent.steer(UserMessage(content=content))
        return CommandReceipt(
            command_id=new_id("cmd"),
            session_id=session_id,
            seq=receipt_msg.seq,
            accepted=True,
        )

    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt:
        entry = self._live.get(session_id)
        if entry is None:
            return await self._reject(session_id, new_id("cmd"), "unknown session")
        from lca.contracts.harness.agent import ContextMessage

        receipt_msg = await entry.handle.agent.inject(
            ContextMessage(content=content, source=source)
        )
        return CommandReceipt(
            command_id=new_id("cmd"),
            session_id=session_id,
            seq=receipt_msg.seq,
            accepted=True,
        )

    async def _reject(self, session_id: str, command_id: str, reason: str) -> CommandReceipt:
        entry = self._live.get(session_id)
        seq = -1
        if entry is not None:
            event = await entry.store.append(CommandRejected(command_type="unknown", reason=reason))
            seq = event.seq
        return CommandReceipt(
            command_id=command_id,
            session_id=session_id,
            seq=seq,
            accepted=False,
            rejection_reason=reason,
        )

    @staticmethod
    def _status_from_store(store: SessionStore) -> str:
        for event in reversed(store.events()):
            if event.type == "session.checkpoint.v1":
                return str(event.data.get("status") or "idle")
            if event.type == "turn.ended.v1" and event.data.get("reason") == "waiting_input":
                return "waiting_input"
        return "idle"
