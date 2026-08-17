"""1:1 port of ``@deepseek-ai/dsh-session/types``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NewType, Union

from lca.layer0_infra.dsh_core.session._llm_types import (
    LlmCallConfig,
    LlmCallConfigAdapterDefaults,
    LlmFailure,
    ToolSchema,
    UserMessage,
)
from lca.layer0_infra.dsh_core.session.json_ import JsonValue

# Re-export for the wire-contract surface
__all__ = [
    "SESSION_FORMAT_VERSION",
    "AgentCancelCause",
    "CreateSessionOptions",
    "EpochHeader",
    "JsonValue",
    "PrepareSessionOptions",
    "ReplaceSurfaceOp",
    "RequestContext",
    "RequestHeaderReason",
    "RestoredSessionOptions",
    "SessionEvent",
    "SessionEventMap",
    "SessionEventType",
    "SessionHeader",
    "SessionId",
    "SurfaceEventType",
    "SurfaceIntent",
    "SurfaceOp",
    "TodoItem",
    "TurnEndCancelCause",
    "TurnEndReason",
]

# ---------------------------------------------------------------------------
# Format version
# ---------------------------------------------------------------------------

SESSION_FORMAT_VERSION: int = 0
"""On-disk session format version — single source of truth."""

# ---------------------------------------------------------------------------
# Branded id types
# ---------------------------------------------------------------------------

SessionId = NewType("SessionId", str)


# ---------------------------------------------------------------------------
# SessionHeader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionHeader:
    """Immutable validated storage metadata."""

    version: int
    id: SessionId
    createdAt: int
    cwd: str | None = None
    parentSession: SessionId | None = None
    seedLength: int | None = None
    origin: Literal["subagent"] | None = None
    delegationDepth: int | None = None
    agentPreset: str | None = None


# ---------------------------------------------------------------------------
# CreateSessionOptions / RestoredSessionOptions / PrepareSessionOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SessionEventMeta:
    """Creation metadata supplied by the caller."""

    cwd: str | None = None
    parentSession: SessionId | None = None
    createdAt: int | None = None
    seedLength: int | None = None
    origin: Literal["subagent"] | None = None
    delegationDepth: int | None = None
    agentPreset: str | None = None


@dataclass(frozen=True)
class CreateSessionOptions:
    """Options for creating a Session via the store."""

    seed: tuple[Any, ...] | None = None
    meta: _SessionEventMeta | None = None


@dataclass(frozen=True)
class RestoredSessionOptions:
    """Fresh storage values transferred to SessionStore.prepare."""

    seed: list[Any]
    meta: SessionHeader
    seedSource: Literal["persistence"] = "persistence"


PrepareSessionOptions = Union[CreateSessionOptions, RestoredSessionOptions]

# ---------------------------------------------------------------------------
# AgentCancelCause / TurnEndCancelCause / TurnEndReason
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CancelUser:
    kind: Literal["user"] = "user"


@dataclass(frozen=True)
class CancelParent:
    kind: Literal["parent"] = "parent"


@dataclass(frozen=True)
class CancelHook:
    kind: Literal["hook"] = "hook"
    reason: str = ""


@dataclass(frozen=True)
class CancelDisposed:
    kind: Literal["disposed"] = "disposed"


AgentCancelCause = Union[CancelUser, CancelParent, CancelHook, CancelDisposed]


@dataclass(frozen=True)
class CancelLegacy:
    kind: Literal["legacy"] = "legacy"


TurnEndCancelCause = Union[AgentCancelCause, CancelLegacy]


@dataclass(frozen=True)
class TurnEndCompleted:
    kind: Literal["completed"] = "completed"


@dataclass(frozen=True)
class TurnEndAborted:
    kind: Literal["aborted"] = "aborted"
    reason: TurnEndCancelCause | None = None


@dataclass(frozen=True)
class TurnEndBlocked:
    kind: Literal["blocked"] = "blocked"


@dataclass(frozen=True)
class TurnEndError:
    kind: Literal["error"] = "error"
    error: LlmFailure | None = None


@dataclass(frozen=True)
class TurnEndMaxTokens:
    kind: Literal["max-tokens"] = "max-tokens"


@dataclass(frozen=True)
class TurnEndInterrupted:
    kind: Literal["interrupted"] = "interrupted"


TurnEndReason = Union[
    TurnEndCompleted,
    TurnEndAborted,
    TurnEndBlocked,
    TurnEndError,
    TurnEndMaxTokens,
    TurnEndInterrupted,
]

# ---------------------------------------------------------------------------
# TodoItem
# ---------------------------------------------------------------------------


@dataclass
class TodoItem:
    """One entry in an agent's todo list."""

    content: str
    status: Literal["pending", "in_progress", "completed"]


# ---------------------------------------------------------------------------
# EpochHeader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EpochHeader:
    """Logged request state outside derived history."""

    config: LlmCallConfig
    adapterDefaults: LlmCallConfigAdapterDefaults | None = None
    system: str | None = None
    tools: list[ToolSchema] | None = None


# ---------------------------------------------------------------------------
# RequestContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Registration-bound metadata for one resolved model route."""

    provider: str
    model: str
    contextWindow: int | None = None


# ---------------------------------------------------------------------------
# RequestHeaderReason
# ---------------------------------------------------------------------------

RequestHeaderReason = Literal["initial", "resume", "change"]

# ---------------------------------------------------------------------------
# SurfaceOp / SurfaceIntent / SurfaceEventType
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplaceSurfaceOp:
    """Positional replacement of a surface range [start, end] inclusive."""

    op: Literal["replace"] = "replace"
    start: int = 0
    end: int = 0


SurfaceOp = Union[Literal["append"], ReplaceSurfaceOp]

SurfaceEventType = Literal[
    "user/message",
    "assistant/message",
    "tool/result",
]

# ---------------------------------------------------------------------------
# SessionEventMap  (merge-extensible dictionary)
# ---------------------------------------------------------------------------

SessionEventMap: dict[str, type] = {
    "turn/start": dict,
    "turn/end": dict,
    "step/start": dict,
    "step/end": dict,
    "user/message": UserMessage,
    "assistant/chunk": dict,
    "assistant/message": dict,
    "tool/call": dict,
    "tool/result": dict,
    "todo/write": dict,
    "request/header": dict,
    "request/context": RequestContext,
    "session/end-seed": dict,
}

SessionEventType = Literal[
    "turn/start",
    "turn/end",
    "step/start",
    "step/end",
    "user/message",
    "assistant/chunk",
    "assistant/message",
    "tool/call",
    "tool/result",
    "todo/write",
    "request/header",
    "request/context",
    "session/end-seed",
]

# ---------------------------------------------------------------------------
# SurfaceIntent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceIntent:
    """Surface placement and cited source-event seqs for Session.append."""

    surfaceOp: SurfaceOp | None = None
    sourceEventSeqs: list[int] | None = None


# ---------------------------------------------------------------------------
# SessionEvent  (discriminated by ``type``)
# ---------------------------------------------------------------------------


@dataclass
class SessionEvent:
    """One mutable entry in the session log.

    Frozen after acceptance; the mutable dataclass lets the store build it
    before freezing.  Discriminated union over ``type``.
    """

    type: str
    seq: int
    time: int
    data: Any = None
    ignorable: Literal[True] | None = None
    # Surface-only fields (present only for SurfaceEventType variants):
    surfaceOp: SurfaceOp | None = None
    sourceEventSeqs: list[int] | None = None
