"""Tests for AutoReviewWrappedTool — ADR-0248 工具执行 seam 的 AutoReview 包装。

验证 enforce 模式拦截危险 Shell、放行低风险调用、off 模式零侵入透传，
且包装器保持内层 Tool 的协议表面（name/parameters/幂等/校验）。
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from lca.contracts.models.auto_review.models import AutoReviewMode
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.auto_review.gate import AutoReviewGate
from lca.infrastructure.auto_review.wrapped_tool import AutoReviewWrappedTool


class _EchoShellTool(Tool):
    """最小 Tool 桩：原样回显 command 参数。"""

    name: ClassVar[str] = "run_shell"
    description: ClassVar[str] = "run a shell command"
    parameters: ClassVar[dict[str, Any]] = {"type": "object"}
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        return Observation(
            observation_id="obs-echo",
            success=True,
            payload={"command": args.get("command")},
        )


def _run(coro):
    return asyncio.run(coro)


def test_enforce_blocks_dangerous_command() -> None:
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    wrapped = AutoReviewWrappedTool(_EchoShellTool(), gate)
    obs = _run(wrapped.execute({"command": "cat /etc/shadow"}))
    assert obs.success is False
    assert "shadow" in obs.error.lower() or "敏感" in obs.error


def test_enforce_allows_safe_command() -> None:
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    wrapped = AutoReviewWrappedTool(_EchoShellTool(), gate)
    obs = _run(wrapped.execute({"command": "ls /tmp"}))
    assert obs.success is True
    assert obs.payload == {"command": "ls /tmp"}


def test_off_mode_passthrough() -> None:
    gate = AutoReviewGate(mode=AutoReviewMode.OFF)
    wrapped = AutoReviewWrappedTool(_EchoShellTool(), gate)
    obs = _run(wrapped.execute({"command": "cat /etc/shadow"}))
    assert obs.success is True


def test_escalate_returns_blocked_with_fingerprint() -> None:
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    wrapped = AutoReviewWrappedTool(_EchoShellTool(), gate)
    obs = _run(wrapped.execute({"command": "rm -rf /home/box/cache"}))
    assert obs.success is False
    assert obs.extra.get("auto_review_action") == "escalate"
    assert obs.extra.get("action_fingerprint")


def test_wrapper_surfaces_inner_tool_contract() -> None:
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    inner = _EchoShellTool()
    wrapped = AutoReviewWrappedTool(inner, gate)
    assert wrapped.name == "run_shell"
    assert wrapped.description == inner.description
    assert wrapped.parameters == inner.parameters
    assert wrapped.is_idempotent is False
    assert wrapped.effect_kind == "ephemeral"
    assert wrapped.default_timeout_s == 30
    assert wrapped.validate({}) is None
