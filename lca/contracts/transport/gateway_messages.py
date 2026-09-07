"""WebSocket message types — mirror of packages/agent-gateway-client/src/types.ts:257-369.

All shapes are byte-compat with the TS source. The Python `model_dump()`
JSON output is the same shape the TS union deserialises from.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Client → Server ──────────────────────────────────────────────────────



class _WireBase(BaseModel):
    """Base for wire-compat types: model_dump() always strips None fields.

    The native TS implementation serialises `interface { x?: string }` by
    omitting `undefined` keys. To stay byte-compat we override model_dump
    here so every wire call site gets the same shape without having to
    remember `exclude_none=True`.
    """

    model_config = ConfigDict(extra="ignore")

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)



class AuthMessage(_WireBase):
    type: Literal["auth"] = "auth"
    token: str
    serverUrl: str | None = None
    tokenType: Literal["jwt", "apiKey"] | None = None


class ResumeMessage(_WireBase):
    type: Literal["resume"] = "resume"
    lastEventId: str
    wantStatus: bool | None = None


class HeartbeatMessage(_WireBase):
    type: Literal["heartbeat"] = "heartbeat"


class InterruptMessage(_WireBase):
    type: Literal["interrupt"] = "interrupt"


class ToolResultMessage(_WireBase):
    type: Literal["tool_result"] = "tool_result"
    toolCallId: str
    success: bool
    content: str
    state: dict | None = None
    error: str | None = None


ClientMessage = Annotated[
    AuthMessage | ResumeMessage | HeartbeatMessage | InterruptMessage | ToolResultMessage,
    Field(discriminator="type"),
]


# ── Server → Client ──────────────────────────────────────────────────────


class AuthSuccess(_WireBase):
    type: Literal["auth_success"] = "auth_success"


class AuthFailed(_WireBase):
    type: Literal["auth_failed"] = "auth_failed"
    reason: str


class AuthExpired(_WireBase):
    type: Literal["auth_expired"] = "auth_expired"


class HeartbeatAck(_WireBase):
    type: Literal["heartbeat_ack"] = "heartbeat_ack"


class SessionComplete(_WireBase):
    type: Literal["session_complete"] = "session_complete"


class ResumeComplete(_WireBase):
    type: Literal["resume_complete"] = "resume_complete"
    status: Literal[
        "running", "waiting_input", "waiting_confirmation",
        "completed", "error", "interrupted",
    ]


class AgentEvent(_WireBase):
    """A single event from the agent runtime stream."""

    type: Literal["agent_event"] = "agent_event"
    id: str | None = None  # Redis stream id; used for lastEventId resume
    event: dict  # AgentStreamEvent — see agent_stream_event.py


ServerMessage = Annotated[
    AuthSuccess | AuthFailed | AuthExpired | HeartbeatAck | AgentEvent | SessionComplete | ResumeComplete,
    Field(discriminator="type"),
]


__all__ = (
    "AgentEvent",
    "AuthExpired",
    "AuthFailed",
    "AuthMessage",
    "AuthSuccess",
    "ClientMessage",
    "HeartbeatAck",
    "HeartbeatMessage",
    "InterruptMessage",
    "ResumeComplete",
    "ResumeMessage",
    "ServerMessage",
    "SessionComplete",
    "ToolResultMessage",
)
