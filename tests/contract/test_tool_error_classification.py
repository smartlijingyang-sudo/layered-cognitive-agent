"""工具错误分类与重试语义契约测试。

验证两条核心不变量：
1. 确定性输入错误（validate 失败 / ToolInputError）不触发重试
2. failure_kind 信号在 Observation → Critic → Reflection 链路中正确传播
"""

from __future__ import annotations

from lca.cognition.brain.critic import SimpleCritic
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ToolExecutionError, ToolInputError
from lca.contracts.models.core.state import AgentState, Budget

# ---------------------------------------------------------------------------
# 1. 错误分类协议本身
# ---------------------------------------------------------------------------


class TestErrorClassification:
    def test_base_error_is_retryable(self) -> None:
        err = ToolExecutionError("transient failure")
        assert err.retryable is True

    def test_input_error_is_not_retryable(self) -> None:
        err = ToolInputError("bad input")
        assert err.retryable is False

    def test_input_error_is_subclass(self) -> None:
        assert issubclass(ToolInputError, ToolExecutionError)


# ---------------------------------------------------------------------------
# 2. Critic: failure_kind 传播到 Reflection
# ---------------------------------------------------------------------------


class TestCriticFailureKind:
    def setup_method(self) -> None:
        self.critic = SimpleCritic()
        self.state = AgentState(trace_id="test", task="test", budget=Budget(), step=3)

    async def test_validation_failure_produces_precise_lesson(self) -> None:
        obs = Observation(
            observation_id="obs_test",
            success=False,
            payload=None,
            error="表达式不能为空",
            extra={"failure_kind": "validation"},
        )
        reflection = await self.critic.critique(self.state, obs)
        assert reflection.verdict == "needs_correction"
        assert "参数不合法" in (reflection.lesson or "")
        assert reflection.extra.get("failure_kind") == "validation"

    async def test_transient_failure_produces_retry_hint(self) -> None:
        obs = Observation(
            observation_id="obs_test",
            success=False,
            payload=None,
            error="connection timeout",
            extra={"failure_kind": "transient"},
        )
        reflection = await self.critic.critique(self.state, obs)
        assert "瞬时性错误" in (reflection.lesson or "")
        assert reflection.extra.get("failure_kind") == "transient"

    async def test_unknown_failure_kind_defaults_to_execution(self) -> None:
        obs = Observation(
            observation_id="obs_test",
            success=False,
            payload=None,
            error="something broke",
        )
        reflection = await self.critic.critique(self.state, obs)
        assert reflection.extra.get("failure_kind") == "execution"

    async def test_success_does_not_include_failure_kind(self) -> None:
        obs = Observation(
            observation_id="obs_test",
            success=True,
            payload=42.0,
        )
        reflection = await self.critic.critique(self.state, obs)
        assert reflection.verdict == "on_track"
        assert "failure_kind" not in reflection.extra
