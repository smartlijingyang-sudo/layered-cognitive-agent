"""Tests for Browser streaming and takeover contract models (INV-BROWSER-01)."""

import pytest
from pydantic import ValidationError

from lca.contracts.models.browser.stream import (
    BrowserControlAction,
    BrowserControlActionType,
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
)


def test_browser_session_summary_immutability() -> None:
    summary = BrowserSessionSummary(
        session_id="sess_123",
        run_id="run_abc",
        url="https://example.com",
        title="Example Domain",
        status=BrowserSessionStatus.IDLE,
        viewport_width=1280,
        viewport_height=800,
        has_active_stream=True,
    )
    assert summary.session_id == "sess_123"
    assert summary.url == "https://example.com"
    assert summary.status == BrowserSessionStatus.IDLE
    assert summary.has_active_stream is True

    # INV-BROWSER-01: 不可变验证
    with pytest.raises(ValidationError):
        summary.url = "https://mutated.com"  # type: ignore[misc]

    # INV-BROWSER-01: 严禁未知字段
    with pytest.raises(ValidationError):
        BrowserSessionSummary(
            session_id="sess_123",
            extra_hacked_field="malicious",  # type: ignore[call-arg]
        )


def test_browser_input_event_contract() -> None:
    event = BrowserInputEvent(
        type=BrowserInputEventType.MOUSE_DOWN,
        x=640.5,
        y=320.0,
        button="left",
    )
    assert event.type == BrowserInputEventType.MOUSE_DOWN
    assert event.x == 640.5
    assert event.button == "left"

    with pytest.raises(ValidationError):
        event.x = 100.0  # type: ignore[misc]

    with pytest.raises(ValidationError):
        BrowserInputEvent(
            type=BrowserInputEventType.MOUSE_DOWN,
            unknown_prop="bar",  # type: ignore[call-arg]
        )


def test_browser_control_action_contract() -> None:
    action = BrowserControlAction(
        type=BrowserControlActionType.NAVIGATE,
        url="https://github.com",
    )
    assert action.type == BrowserControlActionType.NAVIGATE
    assert action.url == "https://github.com"

    # 非法类型验证
    with pytest.raises(ValidationError):
        BrowserControlAction(type="unknown_action")  # type: ignore[arg-type]


def test_browser_session_status_enum_values() -> None:
    expected_statuses = {"idle", "agent_running", "waiting_user_control", "human_takeover", "closed"}
    actual_statuses = {s.value for s in BrowserSessionStatus}
    assert actual_statuses == expected_statuses
