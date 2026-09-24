"""Tests for Browser contract models (ADR-0248 §5.3, §6 / s06, s13)."""

import pytest
from pydantic import ValidationError

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
    DesktopLock,
)


def test_browser_action_model() -> None:
    action = BrowserAction(
        action_type=BrowserActionType.NAVIGATE,
        url="https://example.com",
        timeout_s=15,
    )
    assert action.action_type == BrowserActionType.NAVIGATE
    assert action.url == "https://example.com"
    assert action.timeout_s == 15

    # 不可变与禁止多余字段
    with pytest.raises(ValidationError):
        action.url = "https://other.com"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        BrowserAction(
            action_type=BrowserActionType.NAVIGATE,
            extra="forbidden",  # type: ignore[call-arg]
        )


def test_browser_action_result_model() -> None:
    res = BrowserActionResult(
        action_type=BrowserActionType.NAVIGATE,
        success=True,
        url="https://example.com",
        title="Example Domain",
        text_content="Example Domain text...",
        screenshot_artifact_id="art_123",
    )
    assert res.success is True
    assert res.screenshot_artifact_id == "art_123"
    with pytest.raises(ValidationError):
        res.success = False  # type: ignore[misc]


def test_desktop_lock_model() -> None:
    lock = DesktopLock(
        agent_id="sub_browser_1",
        session_id="sess_001",
        acquired_at_ms=1000,
        ttl_seconds=120,
    )
    assert lock.agent_id == "sub_browser_1"
    assert lock.is_expired(current_time_ms=50_000) is False
    assert lock.is_expired(current_time_ms=125_000) is True

    with pytest.raises(ValidationError):
        lock.ttl_seconds = 60  # type: ignore[misc]
