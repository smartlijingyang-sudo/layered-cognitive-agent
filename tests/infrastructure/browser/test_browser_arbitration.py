"""Tests for BrowserArbitrationEngine (INV-BROWSER-03: 单写所有权互斥与接管状态机)."""

import pytest

from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
)
from lca.infrastructure.browser.arbitration import (
    BrowserArbitrationEngine,
)


def test_arbitration_state_transitions():
    engine = BrowserArbitrationEngine()
    session_id = "sess_arb_01"

    # 1. 默认状态为 IDLE
    assert engine.get_status(session_id) == BrowserSessionStatus.IDLE

    # 2. Agent 启动任务 -> AGENT_RUNNING
    status = engine.start_agent_task(session_id)
    assert status == BrowserSessionStatus.AGENT_RUNNING
    assert engine.get_status(session_id) == BrowserSessionStatus.AGENT_RUNNING

    # 3. 遇到验证码 / 用户接管 -> HUMAN_TAKEOVER
    status = engine.request_human_takeover(session_id, reason="captcha_detected")
    assert status == BrowserSessionStatus.HUMAN_TAKEOVER
    assert engine.get_status(session_id) == BrowserSessionStatus.HUMAN_TAKEOVER

    # 4. 用户交还控制权 -> IDLE
    status = engine.release_to_agent(session_id)
    assert status == BrowserSessionStatus.IDLE

    # 5. 会话关闭 -> CLOSED
    status = engine.close_session(session_id)
    assert status == BrowserSessionStatus.CLOSED


def test_input_arbitration_inv_browser_03():
    """INV-BROWSER-03: AGENT_RUNNING 状态下物理屏蔽所有前端上行输入事件。"""
    engine = BrowserArbitrationEngine()
    session_id = "sess_arb_02"

    click_event = BrowserInputEvent(
        type=BrowserInputEventType.MOUSE_DOWN,
        x=0.5,
        y=0.5,
        button="left",
    )

    # 1. IDLE 状态下不接受前端输入
    dec_idle = engine.evaluate_input(session_id, click_event)
    assert dec_idle.allowed is False
    assert dec_idle.reason == "rejected_session_idle"

    # 2. AGENT_RUNNING 状态下物理拦截并丢弃
    engine.start_agent_task(session_id)
    dec_running = engine.evaluate_input(session_id, click_event)
    assert dec_running.allowed is False
    assert dec_running.reason == "rejected_due_to_agent_busy"

    # 3. HUMAN_TAKEOVER 状态下放行用户操作
    engine.request_human_takeover(session_id)
    dec_takeover = engine.evaluate_input(session_id, click_event)
    assert dec_takeover.allowed is True
    assert dec_takeover.reason is None


@pytest.mark.asyncio
async def test_driver_with_arbitration_blocks_input():
    from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver

    engine = BrowserArbitrationEngine()
    driver = PlaywrightCDPDriver(arbitration_engine=engine)

    session_id = "sess_driver_arb"
    await driver.create_session(session_id)

    click_event = BrowserInputEvent(
        type=BrowserInputEventType.MOUSE_DOWN,
        x=100.0,
        y=200.0,
        button="left",
    )

    # 默认 IDLE 态拒绝
    dispatched = await driver.dispatch_input(session_id, click_event)
    assert dispatched is False

    # 设为 HUMAN_TAKEOVER 态放行
    engine.request_human_takeover(session_id)
    dispatched = await driver.dispatch_input(session_id, click_event)
    assert dispatched is True

    # 设为 AGENT_RUNNING 态拒绝
    engine.start_agent_task(session_id)
    dispatched = await driver.dispatch_input(session_id, click_event)
    assert dispatched is False
