"""工具错误分类与重试语义契约测试。

验证两条核心不变量：
1. 确定性输入错误（validate 失败 / ToolInputError）不触发重试
2. failure_kind 信号在 Observation → Critic → Reflection 链路中正确传播
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from lca.contracts.decision import Observation
from lca.contracts.result import ToolExecutionError, ToolInputError
from lca.contracts.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.state import AgentState, Budget
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.brain.critic import SimpleCritic

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
# 2. CalculatorTool.validate 前置校验
# ---------------------------------------------------------------------------


class TestCalculatorValidate:
    def setup_method(self) -> None:
        self.tool = CalculatorTool()

    def test_empty_expression_rejected(self) -> None:
        assert self.tool.validate({"expression": ""}) is not None

    def test_missing_expression_rejected(self) -> None:
        assert self.tool.validate({}) is not None

    def test_none_expression_rejected(self) -> None:
        assert self.tool.validate({"expression": None}) is not None

    def test_non_string_expression_rejected(self) -> None:
        result = self.tool.validate({"expression": 42})
        assert result is not None
        assert "字符串" in result

    def test_valid_expression_accepted(self) -> None:
        assert self.tool.validate({"expression": "1 + 2"}) is None

    def test_whitespace_only_rejected(self) -> None:
        assert self.tool.validate({"expression": "   "}) is not None


# ---------------------------------------------------------------------------
# 3. SafeExecutor: validate 失败不进入重试循环
# ---------------------------------------------------------------------------


class TestSafeExecutorValidationNoRetry:
    def setup_method(self) -> None:
        self.executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=["calculator"]),
        )
        self.tool = CalculatorTool()
        self.retry_policy = RetryPolicy(max_retries=3, backoff_base_s=0.01)
        self.cache_config = CacheConfig()

    async def test_empty_expression_returns_immediately(self) -> None:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            obs = await self.executor.execute(
                self.tool, {"expression": ""}, self.retry_policy, self.cache_config
            )
            mock_sleep.assert_not_called()

        assert obs.success is False
        assert obs.extra.get("failure_kind") == "validation"

    async def test_missing_expression_returns_immediately(self) -> None:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            obs = await self.executor.execute(self.tool, {}, self.retry_policy, self.cache_config)
            mock_sleep.assert_not_called()

        assert obs.success is False
        assert obs.extra.get("failure_kind") == "validation"


# ---------------------------------------------------------------------------
# 4. SafeExecutor: ToolInputError 不重试
# ---------------------------------------------------------------------------


class TestSafeExecutorInputErrorNoRetry:
    def setup_method(self) -> None:
        self.executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=["calculator"]),
        )
        self.tool = CalculatorTool()
        self.retry_policy = RetryPolicy(max_retries=3, backoff_base_s=0.01)
        self.cache_config = CacheConfig()

    async def test_syntax_error_does_not_retry(self) -> None:
        """'2+' 通过 validate（非空字符串），但 ast.parse 抛 SyntaxError → failure_kind=validation。"""
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            obs = await self.executor.execute(
                self.tool, {"expression": "2+"}, self.retry_policy, self.cache_config
            )
            mock_sleep.assert_not_called()

        assert obs.success is False
        assert obs.extra.get("failure_kind") == "validation"

    async def test_unsupported_ast_node_does_not_retry(self) -> None:
        """列表字面量通过 validate（非空字符串），但 _eval_node 遇到 List 节点 → failure_kind=validation。"""
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            obs = await self.executor.execute(
                self.tool, {"expression": "['128.0 * 1.35']"}, self.retry_policy, self.cache_config
            )
            mock_sleep.assert_not_called()

        assert obs.success is False
        assert obs.extra.get("failure_kind") == "validation"


# ---------------------------------------------------------------------------
# 5. SafeExecutor: 正常执行仍然成功
# ---------------------------------------------------------------------------


class TestSafeExecutorNormalPath:
    def setup_method(self) -> None:
        self.executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=["calculator"]),
        )
        self.tool = CalculatorTool()
        self.retry_policy = RetryPolicy(max_retries=3, backoff_base_s=0.01)
        self.cache_config = CacheConfig()

    async def test_valid_expression_succeeds(self) -> None:
        obs = await self.executor.execute(
            self.tool, {"expression": "2 + 3"}, self.retry_policy, self.cache_config
        )
        assert obs.success is True
        assert obs.payload == 5.0


# ---------------------------------------------------------------------------
# 6. Critic: failure_kind 传播到 Reflection
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
