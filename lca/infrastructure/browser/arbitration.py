"""Browser control arbitration state machine (INV-BROWSER-03 / ADR-0248 §5.3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserSessionStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArbitrationDecision:
    """Input arbitration evaluation result."""

    allowed: bool
    reason: str | None = None


class BrowserArbitrationEngine:
    """Manages browser session control ownership and human takeover state machine."""

    def __init__(self) -> None:
        self._states: dict[str, BrowserSessionStatus] = {}
        self._takeover_reasons: dict[str, str] = {}

    def get_status(self, session_id: str) -> BrowserSessionStatus:
        """获取指定会话当前的仲裁状态，默认为 IDLE。"""
        return self._states.get(session_id, BrowserSessionStatus.IDLE)

    def start_agent_task(self, session_id: str) -> BrowserSessionStatus:
        """AI 开始接管并执行任务：切为 AGENT_RUNNING 态。"""
        self._states[session_id] = BrowserSessionStatus.AGENT_RUNNING
        logger.debug("[Arbitration] Session %s entered AGENT_RUNNING", session_id)
        return BrowserSessionStatus.AGENT_RUNNING

    def request_human_takeover(self, session_id: str, reason: str | None = None) -> BrowserSessionStatus:
        """用户主动点击接管或 AI 遇到验证码/2FA 请求人工协助：切为 HUMAN_TAKEOVER 态。"""
        self._states[session_id] = BrowserSessionStatus.HUMAN_TAKEOVER
        if reason:
            self._takeover_reasons[session_id] = reason
        logger.info("[Arbitration] Session %s entered HUMAN_TAKEOVER (reason=%s)", session_id, reason)
        return BrowserSessionStatus.HUMAN_TAKEOVER

    def release_to_agent(self, session_id: str) -> BrowserSessionStatus:
        """用户交还控制权：切回 IDLE 态。"""
        self._states[session_id] = BrowserSessionStatus.IDLE
        self._takeover_reasons.pop(session_id, None)
        logger.info("[Arbitration] Session %s released by human, now IDLE", session_id)
        return BrowserSessionStatus.IDLE

    def close_session(self, session_id: str) -> BrowserSessionStatus:
        """会话关闭并释放所有状态。"""
        self._states[session_id] = BrowserSessionStatus.CLOSED
        self._takeover_reasons.pop(session_id, None)
        logger.debug("[Arbitration] Session %s CLOSED", session_id)
        return BrowserSessionStatus.CLOSED

    def evaluate_input(self, session_id: str, event: BrowserInputEvent) -> ArbitrationDecision:
        """评估前端上行键鼠输入事件的合法性 (INV-BROWSER-03)。

        - HUMAN_TAKEOVER: 允许用户直接操控；
        - AGENT_RUNNING: 物理屏蔽所有前端输入，防止指令竞争与屏幕状态脏读；
        - IDLE / CLOSED: 默认丢弃。
        """
        status = self.get_status(session_id)
        if status == BrowserSessionStatus.HUMAN_TAKEOVER:
            return ArbitrationDecision(allowed=True)

        if status == BrowserSessionStatus.AGENT_RUNNING:
            logger.debug("[Arbitration] Input dropped on %s due to agent busy (event=%s)", session_id, event.type)
            return ArbitrationDecision(allowed=False, reason="rejected_due_to_agent_busy")

        if status == BrowserSessionStatus.CLOSED:
            return ArbitrationDecision(allowed=False, reason="rejected_session_closed")

        return ArbitrationDecision(allowed=False, reason="rejected_session_idle")


__all__ = [
    "ArbitrationDecision",
    "BrowserArbitrationEngine",
]
