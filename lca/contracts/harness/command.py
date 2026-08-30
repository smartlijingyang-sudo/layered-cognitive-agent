"""Typed commands exchanged across the session spine.

Commands carry a caller-visible identity so ingestion, journal append and
projection consumers can deduplicate the same intent without inspecting the
command payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import uuid4


class CommandKind(StrEnum):
    """Stable wire-level names for commands accepted by the session spine."""

    SESSION_CREATE = "session.create"
    MESSAGE_SEND = "message.send"
    CANCEL = "session.cancel"
    APPROVAL_RESUME = "approval.resume"
    STEER = "session.steer"
    INJECT = "session.inject"


def new_command_id(kind: CommandKind) -> str:
    """Create a unique command identity with a stable kind prefix."""

    return f"{kind.value}:{uuid4().hex}"


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    session_id: str
    seq: int
    accepted: bool
    rejection_reason: str | None = None


@dataclass(frozen=True)
class SessionCreateCommand:
    idempotency_key: str
    profile: str
    preset: str | None = None
    agent_options: dict | None = None
    session_id: str | None = None
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.SESSION_CREATE


@dataclass(frozen=True)
class MessageSendCommand:
    idempotency_key: str
    session_id: str
    role: Literal["user"]
    content: str
    attachments: tuple[str, ...] = ()
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.MESSAGE_SEND


@dataclass(frozen=True)
class CancelCommand:
    session_id: str
    keep_inbox: bool = True
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.CANCEL


@dataclass(frozen=True)
class ApprovalResumeCommand:
    """Resume one persisted approval with an explicit durable identity."""

    session_id: str
    approval_id: str
    payload: str
    idempotency_key: str
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.APPROVAL_RESUME


@dataclass(frozen=True)
class SteerCommand:
    session_id: str
    content: str
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.STEER


@dataclass(frozen=True)
class InjectCommand:
    session_id: str
    source: str
    content: str
    command_id: str = ""

    @property
    def kind(self) -> CommandKind:
        return CommandKind.INJECT


def ensure_command_id(command: object) -> str:
    """Return an existing ID or fail rather than silently deduplicating by payload."""

    command_id = getattr(command, "command_id", "")
    if not isinstance(command_id, str) or not command_id.strip():
        kind = getattr(command, "kind", None)
        if not isinstance(kind, CommandKind):
            raise TypeError("command must expose a CommandKind before dispatch")
        return new_command_id(kind)
    return command_id


@runtime_checkable
class AgentRegistryFacade(Protocol):
    """Command-level view of AgentRegistry. Never exposes LiveAgent."""

    async def create_session(
        self,
        *,
        idempotency_key: str,
        profile: str,
        preset: str | None,
        options: dict | None,
        session_id: str | None = None,
    ) -> CommandReceipt: ...

    async def dispatch_message(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        content: str,
        role: str,
        message_id: str | None = None,
    ) -> CommandReceipt: ...

    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt: ...

    async def resume_approval(
        self,
        *,
        session_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> CommandReceipt: ...

    async def steer(self, *, session_id: str, content: str) -> CommandReceipt: ...

    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt: ...
