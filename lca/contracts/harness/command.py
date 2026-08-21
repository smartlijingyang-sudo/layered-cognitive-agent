"""Typed commands, receipts, and the Gateway-facing registry facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


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


@dataclass(frozen=True)
class MessageSendCommand:
    idempotency_key: str
    session_id: str
    role: Literal["user"]
    content: str
    attachments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CancelCommand:
    session_id: str
    keep_inbox: bool = True


@dataclass(frozen=True)
class AnswerCommand:
    session_id: str
    answer: str


@dataclass(frozen=True)
class SteerCommand:
    session_id: str
    content: str


@dataclass(frozen=True)
class InjectCommand:
    session_id: str
    source: str
    content: str


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
    ) -> CommandReceipt: ...

    async def dispatch_message(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        content: str,
        role: str,
    ) -> CommandReceipt: ...

    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt: ...

    async def answer(self, *, session_id: str, answer: str) -> CommandReceipt: ...

    async def steer(self, *, session_id: str, content: str) -> CommandReceipt: ...

    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt: ...
