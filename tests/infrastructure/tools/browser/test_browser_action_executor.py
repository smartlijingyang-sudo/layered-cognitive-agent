"""Tests for the shared browser-action execution seam (RA-146).

Covers ``build_browser_action_executor``: dispatch to the real browser tool,
payload -> BrowserActionResult recovery, and fail-closed for unbacked actions.
"""

import pytest

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.infrastructure.tools.browser.executor import build_browser_action_executor


class _FakeTool:
    """录制型假工具：断言收到正确的工具参数，返回预设 Observation。"""

    def __init__(self, name: str, observation: Observation) -> None:
        self.name = name
        self._observation = observation
        self.calls: list[dict] = []

    async def execute(self, args: dict) -> Observation:
        self.calls.append(args)
        return self._observation


def _obs(payload, success=True, error=None) -> Observation:
    return Observation(
        observation_id="obs_test",
        success=success,
        payload=payload,
        error=error,
    )


@pytest.mark.asyncio
async def test_executor_dispatches_navigate_and_recovers_real_result():
    """NAVIGATE 分发到 browser_navigate，payload 恢复出真实结果。"""
    expected = BrowserActionResult(
        action_type=BrowserActionType.NAVIGATE,
        success=True,
        url="https://example.com",
        title="Example Domain",
    )
    tool = _FakeTool("browser_navigate", _obs(expected.model_dump()))
    executor = build_browser_action_executor(tools=[tool])

    result = await executor(
        BrowserAction(action_type=BrowserActionType.NAVIGATE, url="https://example.com")
    )

    assert result == expected
    assert tool.calls == [{"url": "https://example.com"}]


@pytest.mark.asyncio
async def test_executor_maps_click_selector_arg():
    """CLICK 映射 selector 参数。"""
    expected = BrowserActionResult(action_type=BrowserActionType.CLICK, success=True)
    tool = _FakeTool("browser_click", _obs(expected.model_dump()))
    executor = build_browser_action_executor(tools=[tool])

    result = await executor(
        BrowserAction(action_type=BrowserActionType.CLICK, selector="#login-btn")
    )

    assert result.success is True
    assert tool.calls == [{"selector": "#login-btn"}]


@pytest.mark.asyncio
async def test_executor_fails_closed_for_unbacked_action():
    """TYPE 没有支撑工具：诚实失败，不伪造。"""
    executor = build_browser_action_executor(tools=[])

    result = await executor(
        BrowserAction(action_type=BrowserActionType.TYPE, text="hello")
    )

    assert result.success is False
    assert result.action_type == BrowserActionType.TYPE
    assert result.error is not None


@pytest.mark.asyncio
async def test_executor_falls_back_to_text_result_on_foreign_payload():
    """payload 非结果字典时回退为诚实文本结果，不抛异常。"""
    tool = _FakeTool("browser_screenshot", _obs("raw-bytes"))
    executor = build_browser_action_executor(tools=[tool])

    result = await executor(BrowserAction(action_type=BrowserActionType.SCREENSHOT))

    assert result.success is True
    assert result.action_type == BrowserActionType.SCREENSHOT
    assert result.text_content == "raw-bytes"
