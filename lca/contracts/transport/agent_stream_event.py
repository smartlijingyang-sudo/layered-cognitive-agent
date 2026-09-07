"""AgentStreamEvent union — mirror of packages/agent-gateway-client/src/types.ts:1-54.

All 18 event types are present. The `data` payload shape matches the TS
interface for the same event type.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _WireBase(BaseModel):
    """Base for wire-compat types: model_dump() always strips None fields.

    The native TS implementation serialises `interface { x?: string }` by
    omitting `undefined` keys. To stay byte-compat we override model_dump
    here so every wire call site gets the same shape without having to
    remember `exclude_none=True`.
    """

    model_config = ConfigDict(extra="ignore")

    def model_dump(self, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)



class AgentRuntimeInit(_WireBase):
    type: Literal["agent_runtime_init"] = "agent_runtime_init"
    data: dict
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentRuntimeEndData(_WireBase):
    finalState: dict
    reason: Literal["completed", "error", "interrupted", "timeout"]
    reasonDetail: str
    phase: Literal["execution_complete"]
    operationId: str | None = None
    uiMessages: list | None = None


class AgentRuntimeEnd(_WireBase):
    type: Literal["agent_runtime_end"] = "agent_runtime_end"
    data: AgentRuntimeEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamStartData(_WireBase):
    assistantMessage: dict  # {id, model, provider, role, parentId, topicId, ...}


class StreamStart(_WireBase):
    type: Literal["stream_start"] = "stream_start"
    data: StreamStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamChunkData(_WireBase):
    chunkType: Literal[
        "text", "reasoning", "tools_calling", "image", "grounding",
        "base64_image", "content_part", "reasoning_part", "tool_state",
    ]
    content: str | None = None
    reasoning: str | None = None
    toolsCalling: list | None = None
    snapshotMode: Literal["append", "replace"] | None = None
    snapshotSeq: int | None = None
    grounding: dict | None = None
    images: list | None = None
    imageList: list | None = None
    reasoningParts: list | None = None
    contentParts: list | None = None


class StreamChunk(_WireBase):
    type: Literal["stream_chunk"] = "stream_chunk"
    data: StreamChunkData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamEndData(_WireBase):
    finalContent: str | None = None
    usage: dict | None = None
    speed: dict | None = None


class StreamEnd(_WireBase):
    type: Literal["stream_end"] = "stream_end"
    data: StreamEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class VisibleOutputEnd(_WireBase):
    type: Literal["visible_output_end"] = "visible_output_end"
    data: dict
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamRetryData(_WireBase):
    attempt: int
    max: int
    provider: str | None = None
    delayMs: int | None = None


class StreamRetry(_WireBase):
    type: Literal["stream_retry"] = "stream_retry"
    data: StreamRetryData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolStartData(_WireBase):
    parentMessageId: str
    toolCalling: dict  # {identifier, apiName, arguments, id, type}


class ToolStart(_WireBase):
    type: Literal["tool_start"] = "tool_start"
    data: ToolStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolEndData(_WireBase):
    isSuccess: bool
    result: dict | None = None
    payload: dict | None = None
    executionTime: int | None = None


class ToolEnd(_WireBase):
    type: Literal["tool_end"] = "tool_end"
    data: ToolEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolExecuteData(_WireBase):
    apiName: str
    identifier: str
    arguments: dict
    toolCallId: str
    toolMessageId: str | None = None
    assistantMessageId: str | None = None
    executionTimeoutMs: int | None = None
    scope: str | None = None
    topicId: str | None = None
    threadId: str | None = None
    taskId: str | None = None
    groupId: str | None = None
    documentId: str | None = None
    sourceMessageId: str | None = None
    agentId: str | None = None
    rootOperationId: str | None = None


class ToolExecute(_WireBase):
    type: Literal["tool_execute"] = "tool_execute"
    data: ToolExecuteData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentInterventionRequestData(_WireBase):
    apiName: str
    identifier: str
    arguments: dict
    toolCallId: str
    deadline: int


class AgentInterventionRequest(_WireBase):
    type: Literal["agent_intervention_request"] = "agent_intervention_request"
    data: AgentInterventionRequestData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentInterventionResponseData(_WireBase):
    toolCallId: str
    result: dict | None = None
    cancelled: bool | None = None
    cancelReason: Literal["timeout", "user_cancelled", "session_ended"] | None = None


class AgentInterventionResponse(_WireBase):
    type: Literal["agent_intervention_response"] = "agent_intervention_response"
    data: AgentInterventionResponseData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StepStartData(_WireBase):
    phase: str | None = None
    requiresApproval: bool | None = None
    pendingToolsCalling: list | None = None
    uiMessages: list | None = None


class StepStart(_WireBase):
    type: Literal["step_start"] = "step_start"
    data: StepStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StepCompleteData(_WireBase):
    phase: str
    finalState: dict | None = None
    reason: str | None = None
    reasonDetail: str | None = None


class StepComplete(_WireBase):
    type: Literal["step_complete"] = "step_complete"
    data: StepCompleteData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class NotifyUpdateData(_WireBase):
    pass


class NotifyUpdate(_WireBase):
    type: Literal["notify_update"] = "notify_update"
    data: NotifyUpdateData = NotifyUpdateData()
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ErrorEventData(_WireBase):
    type: str | None = None
    message: str | None = None
    body: dict | None = None
    provider: str | None = None
    errorType: str | None = None


class ErrorEvent(_WireBase):
    type: Literal["error"] = "error"
    data: ErrorEventData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class HeartbeatData(_WireBase):
    pass


class Heartbeat(_WireBase):
    type: Literal["heartbeat"] = "heartbeat"
    data: HeartbeatData = HeartbeatData()
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


# Full union for type checking
AgentStreamEvent = Annotated[
    AgentRuntimeInit | AgentRuntimeEnd | StreamStart | StreamChunk | StreamEnd | VisibleOutputEnd | StreamRetry | ToolStart | ToolEnd | ToolExecute | AgentInterventionRequest | AgentInterventionResponse | StepStart | StepComplete | NotifyUpdate | ErrorEvent | Heartbeat,
    Field(discriminator="type"),
]


__all__ = (
    "AgentInterventionRequest",
    "AgentInterventionRequestData",
    "AgentInterventionResponse",
    "AgentInterventionResponseData",
    "AgentRuntimeEnd",
    "AgentRuntimeEndData",
    "AgentRuntimeInit",
    "AgentStreamEvent",
    "ErrorEvent",
    "ErrorEventData",
    "Heartbeat",
    "HeartbeatData",
    "NotifyUpdate",
    "NotifyUpdateData",
    "StepComplete",
    "StepCompleteData",
    "StepStart",
    "StepStartData",
    "StreamChunk",
    "StreamChunkData",
    "StreamEnd",
    "StreamEndData",
    "StreamRetry",
    "StreamRetryData",
    "StreamStart",
    "StreamStartData",
    "ToolEnd",
    "ToolEndData",
    "ToolExecute",
    "ToolExecuteData",
    "ToolStart",
    "ToolStartData",
    "VisibleOutputEnd",
)
