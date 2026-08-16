"""DshLiveAgent — wraps DSH execution as a LiveAgent.

Bridges the existing DSH runtime into the harness spine so that DSH
sessions produce the same session events and projections as Cognitive
loop sessions. The gateway and frontend see no difference.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import (
    ContextMessage,
    MessageReceipt,
    UserMessage,
)
from lca.contracts.harness.events import (
    MessageAccepted,
    SessionCheckpoint,
    TurnEnded,
    TurnStarted,
)
from lca.contracts.harness.session import EventScope, SessionEvent
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore
from lca.plugins.loop_dsh_bridge.event_mapping import (
    DshEventMapper,
    to_session_event,
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DshBridgeConfig:
    """Configuration for a DSH bridge session."""

    machine_id: str
    cwd: str
    transport: Any  # MachineTransport
    settings: Any | None = None  # DshSettings
    runs_dir: Path | None = None


class DshLiveAgent:
    """LiveAgent that delegates execution to the DSH runtime.

    Each ``followup`` runs one DSH turn via the existing driver pipeline,
    projecting DSH notifications into SessionEvents along the way.
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        inbox: Inbox,
        config: DshBridgeConfig,
        identity_id: str,
    ) -> None:
        self._store = store
        self._inbox = inbox
        self._config = config
        self._id = identity_id
        self._status = "idle"
        self._turn = 0
        self._cancelled = False
        self._idle = asyncio.Event()
        self._idle.set()
        self._mapper = DshEventMapper(session_id=store.header.id)

    @property
    def id(self) -> str:
        return self._id

    @property
    def session_id(self) -> str:
        return self._store.header.id

    @property
    def status(self) -> str:
        return self._status

    async def followup(self, message: UserMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        msg = UserMessage(content=message.content, role=message.role, message_id=mid)
        await self._inbox.followup(msg)
        self._idle.clear()
        self._status = "working"
        self._turn += 1

        await self._store.append(
            MessageAccepted(
                message_id=mid,
                role=msg.role,
                content_ref=msg.content,
            ),
            actor="user",
        )
        await self._store.append(TurnStarted(turn=self._turn))

        try:
            output, error, reason = await self._run_dsh_turn(msg.content)
        except Exception as exc:
            _log.warning("dsh_bridge_turn_failed", exc_info=True, session_id=self.session_id)
            output = ""
            error = f"{type(exc).__name__}: {exc}"
            reason = "error"

        await self._store.append(TurnEnded(turn=self._turn, reason=reason))
        await self._store.append(
            SessionCheckpoint(
                status="idle" if reason != "error" else "failed",
                snapshot_ref=None,
                answer=output if reason != "error" else None,
                error=error if reason == "error" else None,
            )
        )
        self._status = "idle"
        self._idle.set()

        return MessageReceipt(
            message_id=mid,
            session_id=self.session_id,
            seq=self._store.current_seq,
        )

    async def steer(self, message: UserMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        event = await self._store.append(
            MessageAccepted(message_id=mid, role="user", content_ref=message.content),
            actor="user",
        )
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    async def inject(self, message: ContextMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        event = await self._store.append(
            MessageAccepted(message_id=mid, role="system", content_ref=message.content),
            actor="system",
        )
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None:
        self._cancelled = True
        self._status = "disposed"
        if not keep_inbox:
            self._inbox.state.next_turn.clear()
            self._inbox.state.next_step.clear()
        self._idle.set()

    async def when_idle(self) -> None:
        await self._idle.wait()

    async def _run_dsh_turn(self, question: str) -> tuple[str, str, str]:
        """Execute one DSH turn. Returns (output, error, reason)."""
        from lca.contracts.models.core.conversation import ConversationTurn
        from lca.contracts.models.core.plane import PlaneKind, PlaneRef
        from lca.layer0_infra.dsh.archive import JsonlEventArchive
        from lca.layer0_infra.dsh.projector import DshJournalProjector
        from lca.layer0_infra.dsh.run import run_dsh_machine_turn
        from lca.layer0_infra.dsh.settings import DshSettings
        from lca.layer0_infra.dsh.sink import HandleJournalSink

        cfg = self._config
        settings = cfg.settings if cfg.settings is not None else DshSettings()
        machine = PlaneRef(
            kind=PlaneKind.MACHINE,
            id=cfg.machine_id,
            root=cfg.cwd,
            label="machine",
        )

        # Collect prior turns for conversation context
        prior_turns: list[ConversationTurn] = []
        for ev in self._store.events():
            if ev.type == "message.accepted.v1":
                role = ev.data.get("role", "")
                content = ev.data.get("content_ref", "")
                if role in ("user", "assistant") and content:
                    prior_turns.append(ConversationTurn(role=role, content=content))
        # Remove the current question from prior context
        if prior_turns and prior_turns[-1].content == question:
            prior_turns = prior_turns[:-1]

        runs_dir = cfg.runs_dir or Path.cwd()
        run_id = self.session_id
        archive = JsonlEventArchive(runs_dir / f"{run_id}.dsh.jsonl")

        # Legacy projector for backward-compat SSE / LiveTail
        sink = HandleJournalSink()
        projector = DshJournalProjector(sink)
        projector.ensure_open()

        try:
            result = await run_dsh_machine_turn(
                run_id=run_id,
                question=question,
                prior_turns=prior_turns,
                machine=machine,
                transport=cfg.transport,
                runs_dir=runs_dir,
                settings=settings,
                projector=projector,
                archive=archive,
            )
        except Exception as exc:
            return "", str(exc), "error"

        # Project DSH events into the harness session store for unified projections
        self._project_dsh_events(archive)

        # Emit terminal event into session store
        projector.emit_terminal_event()

        if result.finish_reason not in {None, "completed"}:
            return "", result.finish_reason or "dsh error", "error"
        return result.final_response, "", "completed"

    def _project_dsh_events(self, archive: Any) -> None:
        """Feed archived DSH notifications through the mapper → session store.

        This is a best-effort projection: if the archive doesn't expose
        notifications, we skip (the legacy projector already handled them).
        """
        notifications = getattr(archive, "notifications", None)
        if notifications is None:
            return
        for notification in notifications:
            method = getattr(notification, "method", "")
            payload = getattr(notification, "payload", {})
            mapped = self._mapper.map_notification(method, payload)
            if mapped is None:
                continue
            session_event = to_session_event(mapped, session_id=self.session_id)
            # Write directly with seq allocation
            asyncio.get_event_loop().call_soon(
                lambda ev=session_event: asyncio.ensure_future(self._append_mapped(ev))
            )

    async def _append_mapped(self, event: SessionEvent) -> None:
        """Append a pre-built SessionEvent with seq allocation."""
        async with self._store._seq_lock:
            self._store._seq += 1
            seq = self._store._seq
        stamped = SessionEvent(
            type=event.type,
            seq=seq,
            time=int(time.time() * 1000),
            data=event.data,
            session_id=event.session_id,
            actor=event.actor,
            provider=event.provider,
            visibility=event.visibility,
            scope=EventScope(scope_id=self._store.header.id),
        )
        self._store._events.append(stamped)
        if self._store._persistence is not None:
            self._store._persistence.write_event(stamped)
        for listener in self._store._listeners:
            listener(stamped)
