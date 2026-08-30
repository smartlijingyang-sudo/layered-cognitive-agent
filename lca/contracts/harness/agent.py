"""Agent loop SPI and immutable live-agent recovery contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from lca.contracts.atoms.ids import RunId, TraceId


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


class LiveAgentStatus(StrEnum):
    """The small lifecycle vocabulary exposed by a live Session Spine agent."""

    IDLE = "idle"
    WORKING = "working"
    WAITING_INPUT = "waiting_input"
    DISPOSED = "disposed"


@dataclass(frozen=True)
class ApprovalResumePoint:
    """Durable minimum needed to resume one approval-paused declarative run."""

    approval_id: str
    snapshot_id: str
    step: int
    state_ref: str
    plan_ref: str
    node_id: str
    visit_counts: tuple[tuple[str, int], ...]
    edge_counts: tuple[tuple[str, str, int], ...]
    artifacts: Mapping[str, object]
    causation_refs: tuple[str, ...]
    budget_snapshot: Mapping[str, int]
    # Optional for journal records created before recovery correlation was added.
    trace_id: TraceId = ""  # type: ignore[assignment]
    run_id: RunId = ""  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.approval_id.strip():
            raise ValueError("approval_id must not be empty")
        if not self.snapshot_id.strip() or not self.state_ref.strip():
            raise ValueError("resume point requires a snapshot_id and state_ref")
        if not self.plan_ref.strip() or not self.node_id.strip():
            raise ValueError("resume point requires a plan_ref and node_id")
        if self.step < 0:
            raise ValueError("resume point step must be non-negative")


@dataclass(frozen=True)
class LiveAgentRecovery:
    """The complete durable lifecycle view supplied when a live agent is rebuilt."""

    status: LiveAgentStatus = LiveAgentStatus.IDLE
    completed_turns: int = 0
    pending_resume: ApprovalResumePoint | None = None

    def __post_init__(self) -> None:
        if self.completed_turns < 0:
            raise ValueError("completed_turns must be non-negative")
        if self.status is LiveAgentStatus.WAITING_INPUT and self.pending_resume is None:
            raise ValueError("waiting_input recovery requires a pending approval resume point")
        if self.status is not LiveAgentStatus.WAITING_INPUT and self.pending_resume is not None:
            raise ValueError(
                "only waiting_input recovery may retain a pending approval resume point"
            )


@runtime_checkable
class LiveAgent(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def status(self) -> LiveAgentStatus: ...

    def restore(self, recovery: LiveAgentRecovery) -> None: ...

    async def followup(self, message: UserMessage) -> MessageReceipt: ...

    async def resume_approval(
        self,
        approval_id: str,
        payload: str,
        *,
        idempotency_key: str,
    ) -> MessageReceipt: ...

    async def steer(self, message: UserMessage) -> MessageReceipt: ...

    async def inject(self, message: ContextMessage) -> MessageReceipt: ...

    async def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None: ...

    async def when_idle(self) -> None: ...


@runtime_checkable
class AgentHandle(Protocol):
    @property
    def agent(self) -> LiveAgent: ...

    async def dispose(self, reason: str = "owner") -> None: ...


@runtime_checkable
class SessionLiveBuilder(Protocol):
    """Build one live Session agent from durable facts and the active Profile scope."""

    def __call__(
        self,
        store: object,
        inbox: object,
        identity_id: str,
        options: dict[str, object] | None,
        cordis_ctx: object | None = None,
    ) -> AgentHandle: ...


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


__all__ = [
    "AgentHandle",
    "AgentIdentity",
    "AgentLoopFactory",
    "AgentOptions",
    "ApprovalResumePoint",
    "ContextMessage",
    "LiveAgent",
    "LiveAgentRecovery",
    "LiveAgentStatus",
    "MessageReceipt",
    "SessionLiveBuilder",
    "UserMessage",
]
