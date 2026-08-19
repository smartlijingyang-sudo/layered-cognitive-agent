"""SessionEventType enum contract tests."""
from lca.contracts.observability.session_events import SessionEventType


def test_session_event_type_is_string_enum():
    """SessionEventType members are str values, matching cordis event names."""
    assert SessionEventType.SESSION_CREATED == "session/created"
    assert SessionEventType.ASSISTANT_MESSAGE == "assistant/message"
    assert SessionEventType.TOOL_CALL == "tool/call"


def test_session_event_type_covers_minimum_surface():
    """session everything 原则: 至少 8 类事件被枚举"""
    required = [
        "SESSION_CREATED",
        "ASSISTANT_MESSAGE",
        "TOOL_CALL",
        "TOOL_RESULT",
        "TURN_START",
        "STEP_START",
        "LLM_REQUEST",
        "GUARD_REJECTED",
    ]
    for name in required:
        assert hasattr(SessionEventType, name)
