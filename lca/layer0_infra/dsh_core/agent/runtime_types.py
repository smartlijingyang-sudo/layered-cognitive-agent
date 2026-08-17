"""1:1 port of ``@deepseek-ai/dsh-agent/runtime-types.ts``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, Union

from lca.layer0_infra.dsh_core.session._llm_types import (
    LlmFailure,
    UserMessage,
)
from lca.layer0_infra.dsh_core.session.types import (
    AgentCancelCause,
    SessionEvent,
    SessionId,
)

if TYPE_CHECKING:
    from lca.layer0_infra.dsh_core.agent.inbox import Inbox
    from lca.layer0_infra.dsh_core.session import Session

# Re-export for convenience
__all__ = [
    "Agent",
    "AgentCancelCause",
    "AgentOptions",
    "AgentStatus",
    "CancelOptions",
    "PreStepDecision",
    "RequestErrorAction",
    "SessionStartSource",
]

# ---------------------------------------------------------------------------
# AgentOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentOptions:
    """Merge-extensible agent creation options.  Persona belongs to system-prompt sections."""

    provider: str | None = None
    """Provider route (must have a registered adapter at call time)."""
    model: str | None = None
    """Model id interpreted by the selected provider adapter."""
    max_tokens: int | None = None
    """Maximum output tokens for each conversation-model request."""


# ---------------------------------------------------------------------------
# CancelOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CancelOptions:
    """Options for :meth:`Agent.cancel`."""

    keep_inbox: bool | None = None
    """Preserve queued and steering inbox items instead of discarding them.

    The active turn is still aborted, but un-started and pending work survives
    for a later turn and no canceled inbox splice is logged.
    """


# ---------------------------------------------------------------------------
# AgentStatus
# ---------------------------------------------------------------------------

AgentStatus = Literal["idle", "running"]
"""An agent's lifecycle state, emitted on every transition as ``agent/status``.

- ``idle``: no driver is active.
- ``running``: begins when waking input starts cancellable pre-step processing
  and lasts while the driver drains, closes, or checkpoints turns.
"""


# ---------------------------------------------------------------------------
# PreStepDecision
# ---------------------------------------------------------------------------

PreStepDecision = Union["_PreStepReject", "_PreStepEnter"]
"""Whether and with which messages the loop enters a proposed step."""


@dataclass(frozen=True)
class _PreStepReject:
    kind: Literal["reject"] = "reject"


@dataclass(frozen=True)
class _PreStepEnter:
    kind: Literal["enter"] = "enter"
    messages: tuple[UserMessage, ...] = ()


def pre_step_reject() -> PreStepDecision:
    """Build a reject decision."""
    return _PreStepReject()


def pre_step_enter(messages: list[UserMessage]) -> PreStepDecision:
    """Build an enter decision with the given messages."""
    return _PreStepEnter(messages=tuple(messages))


# ---------------------------------------------------------------------------
# RequestErrorAction
# ---------------------------------------------------------------------------

RequestErrorAction = Union["_RetryAction", None]
"""Action returned by a listener that owns model-request recovery."""


@dataclass(frozen=True)
class _RetryAction:
    kind: Literal["retry"] = "retry"


def retry_action() -> _RetryAction:
    """Build a retry action."""
    return _RetryAction()


# ---------------------------------------------------------------------------
# SessionStartSource
# ---------------------------------------------------------------------------

SessionStartSource = Literal["startup", "resume", "clear", "compact"]
"""Why a session lifecycle began; seeded creates are ``startup``."""


# ---------------------------------------------------------------------------
# Session Protocol — public live-session handle
# ---------------------------------------------------------------------------


class Session(Protocol):
    """Public live-session handle — the durable log and its metadata."""

    @property
    def id(self) -> SessionId: ...

    @property
    def events(self) -> list[SessionEvent]: ...

    @property
    def header(self) -> Any: ...

    def append(self, event_type: str, data: Any) -> SessionEvent: ...


# ---------------------------------------------------------------------------
# Agent Protocol — public live-agent handle
# ---------------------------------------------------------------------------


class Agent(Protocol):
    """Public live-agent handle.

    Drives a session's turn/step loop, owns an inbox projection, and exposes
    lifecycle management through cancellation and idle-awaiting.
    """

    @property
    def id(self) -> SessionId:
        """The single identity shared with the session."""
        ...

    @property
    def options(self) -> AgentOptions:
        """The provider route and model this agent's requests use."""
        ...

    @property
    def session(self) -> Session:
        """The live session this agent drives; its log is the durable source of truth."""
        ...

    @property
    def inbox(self) -> Inbox:
        """The agent-owned projection of durable pending work."""
        ...

    @property
    def status(self) -> AgentStatus:
        """The current lifecycle state, mirrored on every ``agent/status`` transition."""
        ...

    @property
    def ctx(self) -> Any:
        """Agent-scoped context; contributions are agent-local, unwind on disposal."""
        ...

    def cancel(self, cause: AgentCancelCause, options: CancelOptions | None = None) -> None:
        """Clear queued work and abort the active turn or between-turn task.

        The first cause wins for that activity.  With no active activity,
        cancellation is a no-op and does not arm later work.
        """
        ...

    async def when_idle(self) -> None:
        """Resolve after the current whole-agent activity reaches quiescence."""
        ...

    async def run_maintenance(self, task: Any) -> Any:
        """Run one non-turn maintenance task from the true idle phase."""
        ...

    def send(self, message: UserMessage, target: str, wakeup: bool) -> None:
        """Route identified input to an inbox boundary and optionally wake the driver."""
        ...

    def followup(self, message: UserMessage) -> None:
        """Queue an ordinary follow-up turn and wake the driver."""
        ...

    def steer(self, message: UserMessage) -> None:
        """Submit steering for the nearest step."""
        ...

    def inject(self, message: UserMessage) -> None:
        """Queue model-facing context for the next pre-step without waking the driver."""
        ...


# ---------------------------------------------------------------------------
# Event names and payload types
# ---------------------------------------------------------------------------
# In Python the Cordis event bus is string-keyed.  We define event names as
# constants and payload dataclasses.  Dispatch mode is documented per event.


# -- lifecycle (emit) --

EVENT_AGENT_CREATED = "agent/created"
"""A fully configured agent and live session were published.  @mode emit"""

EVENT_AGENT_DISPOSED = "agent/disposed"
"""An agent left the registry.  @mode emit"""

EVENT_AGENT_STATUS = "agent/status"
"""Agent status changed (idle ↔ running).  @mode emit"""

EVENT_AGENT_INBOX_INSERTED = "agent/inbox/inserted"
"""One message entered the live inbox.  @mode emit"""

EVENT_AGENT_INBOX_CLAIMED = "agent/inbox/claimed"
"""One message left the inbox inside its open turn.  @mode emit"""

EVENT_AGENT_INBOX_DISCARDED = "agent/inbox/discarded"
"""One message was discarded from the live inbox.  @mode emit"""

# -- session lifecycle (emit) --

EVENT_AGENT_SESSION_START = "agent/session-start"
"""The session lifecycle began, once before the first turn.  @mode emit"""

# -- the machine's extension points --

EVENT_AGENT_PRE_STEP = "agent/pre-step"
"""Reject a proposed step or replace the messages that enter it.  @mode waterfall"""

EVENT_AGENT_REQUEST = "agent/request"
"""Replace the frozen call configuration.  @mode waterfall"""

EVENT_AGENT_REQUEST_ERROR = "agent/request-error"
"""Handle one failed model-request attempt.  @mode waterfall"""

EVENT_AGENT_TURN_STOPPING = "agent/turn-stopping"
"""The turn is about to close.  @mode serial"""

# -- error notifications (emit) --

EVENT_AGENT_ERROR = "agent/error"
"""A step or turn errored.  @mode emit"""


# ---------------------------------------------------------------------------
# Event payload dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentCreatedPayload:
    """Payload for ``agent/created``."""

    agent: Any  # Agent — forward reference to avoid circular import at runtime


@dataclass(frozen=True)
class AgentDisposedPayload:
    """Payload for ``agent/disposed``."""

    agent: Any


@dataclass(frozen=True)
class AgentStatusPayload:
    """Payload for ``agent/status``."""

    agent: Any
    status: AgentStatus


@dataclass(frozen=True)
class AgentInboxInsertedPayload:
    """Payload for ``agent/inbox/inserted``."""

    agent: Any
    message: UserMessage


@dataclass(frozen=True)
class AgentInboxClaimedPayload:
    """Payload for ``agent/inbox/claimed``."""

    agent: Any
    message: UserMessage
    turn: int


@dataclass(frozen=True)
class AgentInboxDiscardedPayload:
    """Payload for ``agent/inbox/discarded``."""

    agent: Any
    message: UserMessage


@dataclass(frozen=True)
class AgentSessionStartPayload:
    """Payload for ``agent/session-start``."""

    agent: Any
    source: SessionStartSource


@dataclass(frozen=True)
class AgentPreStepPayload:
    """Payload for ``agent/pre-step`` (waterfall)."""

    agent: Any
    messages: tuple[UserMessage, ...]
    turn: int
    step: int
    signal: Any  # AbortSignal equivalent


@dataclass(frozen=True)
class AgentRequestPayload:
    """Payload for ``agent/request`` (waterfall)."""

    agent: Any
    turn: int
    step: int
    signal: Any  # AbortSignal equivalent


@dataclass(frozen=True)
class AgentRequestErrorPayload:
    """Payload for ``agent/request-error`` (waterfall)."""

    agent: Any
    turn: int
    step: int
    provider: str
    failure: LlmFailure
    retry_policy: Any | None = None  # ResolvedRetryPolicy | None
    signal: Any = None  # AbortSignal equivalent


@dataclass(frozen=True)
class AgentTurnStoppingPayload:
    """Payload for ``agent/turn-stopping`` (serial)."""

    agent: Any
    turn: int
    signal: Any  # AbortSignal equivalent


@dataclass(frozen=True)
class AgentErrorPayload:
    """Payload for ``agent/error`` (emit)."""

    agent: Any
    turn: int
    step: int
    error: BaseException
