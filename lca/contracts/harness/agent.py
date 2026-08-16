"""Agent loop SPI (spec §2.2.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AgentIdentity:
    session_id: str
    parent_session: str | None = None
    delegation_depth: int = 0
    origin: str | None = None


@dataclass(frozen=True)
class AgentOptions:
    provider: str | None = None
    model: str | None = None
    max_steps: int | None = None
    max_tokens: int | None = None
    tools_allow: tuple[str, ...] | None = None
    tools_deny: tuple[str, ...] | None = None


@dataclass(frozen=True)
class UserMessage:
    content: str
    role: str = "user"
    message_id: str = ""


@dataclass(frozen=True)
class ContextMessage:
    content: str
    source: str
    message_id: str = ""


@dataclass(frozen=True)
class MessageReceipt:
    message_id: str
    session_id: str
    seq: int


@runtime_checkable
class LiveAgent(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def status(self) -> str: ...

    async def followup(self, message: UserMessage) -> MessageReceipt: ...

    async def steer(self, message: UserMessage) -> MessageReceipt: ...

    async def inject(self, message: ContextMessage) -> MessageReceipt: ...

    def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None: ...

    async def when_idle(self) -> None: ...


@runtime_checkable
class AgentHandle(Protocol):
    @property
    def agent(self) -> LiveAgent: ...

    async def dispose(self, reason: str = "owner") -> None: ...


@runtime_checkable
class AgentLoopFactory(Protocol):
    async def create(
        self,
        scope: object,
        identity: AgentIdentity,
        options: AgentOptions,
        *,
        resume_session: str | None = None,
    ) -> AgentHandle: ...
