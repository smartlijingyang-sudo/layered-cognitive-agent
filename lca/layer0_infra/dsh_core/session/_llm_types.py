"""1:1 port of ``@deepseek-ai/dsh-llm`` type face needed by the session package.

This is a minimal, self-contained stub — the full ``dsh-llm`` Python port
will eventually supersede it.  Every symbol re-exported here mirrors the
TypeScript interface or branded type the session code depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType, Union

# ---------------------------------------------------------------------------
# Branded id types (TS: ``Branded<'CallId'>`` etc.)
# ---------------------------------------------------------------------------

CallId = NewType("CallId", str)
MessageId = NewType("MessageId", str)


def _CallId(id: str) -> CallId:
    return CallId(id)


def _MessageId(id: str) -> MessageId:
    return MessageId(id)


# Re-export under the TS-mirroring names so downstream code reads identically.
CallId_ = _CallId
MessageId_ = _MessageId

# ---------------------------------------------------------------------------
# Message source discriminated union
# ---------------------------------------------------------------------------

ModelSource = Literal["model"]
ToolSource = Literal["tool"]
UserSource = Literal["user"]

# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextBlock:
    type: Literal["text"]
    text: str


@dataclass(frozen=True)
class ToolCallBlock:
    type: Literal["tool-call"]
    id: CallId
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResultContentBlock:
    type: Literal["tool-result"]
    toolCallId: CallId
    isError: bool
    content: list[TextBlock]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserMessage:
    id: MessageId
    role: Literal["user"]
    source: dict[str, object]  # {kind: str, ...}
    content: list[TextBlock]


@dataclass(frozen=True)
class AssistantMessage:
    id: MessageId
    role: Literal["assistant"]
    source: dict[str, object]  # {kind: 'model', provider, model}
    content: list[TextBlock | ToolCallBlock]


@dataclass(frozen=True)
class ToolResultMessage:
    id: MessageId
    role: Literal["user"]
    source: dict[str, object]  # {kind: 'tool', callId}
    content: list[ToolResultContentBlock]


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


def freeze_message(msg: Message) -> Message:
    """Identity — frozen dataclasses are already immutable."""
    return msg


# ---------------------------------------------------------------------------
# Stream chunks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextDelta:
    type: Literal["text-delta"]
    index: int
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    type: Literal["reasoning-delta"]
    index: int
    text: str


@dataclass(frozen=True)
class ToolCallDelta:
    type: Literal["tool-call-delta"]
    index: int
    id: CallId
    argumentsDelta: str
    name: str | None = None


@dataclass(frozen=True)
class StreamBlockStart:
    type: Literal["block-start"]
    index: int


@dataclass(frozen=True)
class StreamBlockEnd:
    type: Literal["block-end"]
    index: int


@dataclass(frozen=True)
class StreamUsage:
    type: Literal["usage"]


@dataclass(frozen=True)
class StreamFinish:
    type: Literal["finish"]


StreamChunk = Union[
    TextDelta, ReasoningDelta, ToolCallDelta,
    StreamBlockStart, StreamBlockEnd, StreamUsage, StreamFinish,
]

# ---------------------------------------------------------------------------
# Token usage (session-log face, distinct from contracts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    promptTokens: int | None = None
    completionTokens: int | None = None
    cachedTokens: int | None = None


# ---------------------------------------------------------------------------
# Tool schema (opaque to the session layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str = ""
    inputSchema: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM call configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmCallConfig:
    provider: str
    model: str
    reasoningEffort: str | None = None
    maxTokens: int | None = None
    temperature: float | None = None
    topP: float | None = None


@dataclass(frozen=True)
class LlmCallConfigAdapterDefaults:
    reasoningEffort: bool = False
    maxTokens: bool = False


def call_config_equals(a: LlmCallConfig, b: LlmCallConfig) -> bool:
    """Field-wise equality over call configs."""
    return (
        a.provider == b.provider
        and a.model == b.model
        and a.reasoningEffort == b.reasoningEffort
        and a.maxTokens == b.maxTokens
        and a.temperature == b.temperature
        and a.topP == b.topP
    )


# ---------------------------------------------------------------------------
# LLM failure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmFailure:
    message: str
    code: str = "UNKNOWN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_never(value: object, context: str = "") -> object:
    """Exhaustiveness sentinel — ``typing.assert_never`` equivalent."""
    raise AssertionError(f"{context}: unexpected value {value!r}")


def deep_freeze(obj: object) -> object:
    """Identity for already-frozen dataclasses; recurses into plain dicts/lists."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, (list, tuple)):
        return tuple(deep_freeze(item) for item in obj)
    if isinstance(obj, dict):
        return {k: deep_freeze(v) for k, v in obj.items()}
    return obj
