"""Session event type enum — the single taxonomy of session mutations.

"session everything" 原则: any state mutation corresponds to a SessionEventType.
"""

from __future__ import annotations

from enum import Enum


class SessionEventType(str, Enum):
    """session 任何状态变更。"""

    # Session 生命周期
    SESSION_CREATED = "session/created"
    SESSION_DISPOSED = "session/disposed"
    SESSION_FLUSHED = "session/flushed"

    # Attachment
    ATTACHMENT_ADDED = "attachment/added"
    ATTACHMENT_REMOVED = "attachment/removed"
    ATTACHMENT_STAGED = "attachment/staged"

    # User / Assistant
    USER_MESSAGE_ACCEPTED = "user/message/accepted"
    ASSISTANT_MESSAGE = "assistant/message"

    # Turn / Step
    TURN_START = "turn/start"
    TURN_END = "turn/end"
    STEP_START = "step/start"
    STEP_END = "step/end"

    # LLM
    LLM_REQUEST = "llm/request"
    LLM_RESPONSE_CHUNK = "llm/response/chunk"
    LLM_RESPONSE = "llm/response"
    LLM_ERROR = "llm/error"

    # Tool
    TOOL_CALL = "tool/call"
    TOOL_PRE_EXECUTE = "tool/pre-execute"
    TOOL_POST_EXECUTE = "tool/post-execute"
    TOOL_RESULT = "tool/result"
    TOOL_ERROR = "tool/error"

    # Guards
    GUARD_REJECTED = "guard/rejected"
    LOOP_INTERVENTION = "loop/intervention"
    BUDGET_EXCEEDED = "budget/exceeded"

    # Subagent / Delegation
    SUBAGENT_START = "subagent/start"
    SUBAGENT_END = "subagent/end"
    DELEGATION_SENT = "delegation/sent"

    # Transport / Sandbox
    SANDBOX_VIOLATION = "sandbox/violation"
    TRANSPORT_ERROR = "transport/error"
