"""INV-03: Tool result true exit code and duration invariant tests.

Validates that:
1. `record_step_tool_result` accepts and emits `exit_code: int`.
2. SafeExecutor extracts real exit_code from observation (payload/extra) and propagates it to `step.tool_result.record`.
3. Tool failure yields non-zero exit_code (e.g. exit_code=127 or default 1 for failures).
4. `latency_ms` is preserved and positive.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)
from lca.contracts.protocols.runtime.infra.infra import Tool


def test_safe_executor_propagates_true_exit_code_on_success() -> None:
    """Successful tool execution records exit_code=0 in step.tool_result.record."""
    mock_tool = MagicMock(spec=Tool)
    mock_tool.name = "executeCode"
    mock_tool.validate = MagicMock(return_value=None)
    mock_tool.execute = AsyncMock(
        return_value=Observation(
            observation_id="obs_succ",
            success=True,
            payload={"output": "hello world", "exit_code": 0},
        )
    )

    with patch("lca.loop.commit.tool_journal.publish_ep_bound") as mock_publish:
        from lca.cognition.body.executor.safe_executor.executor import SimpleSafeExecutor

        executor = SimpleSafeExecutor(
            permission_manifest=ToolPermissionManifest(allowed_tools=["executeCode"])
        )
        obs = asyncio.run(
            executor.execute(
                mock_tool,
                {"code": "print('hello')"},
                retry_policy=RetryPolicy(max_retries=0),
                cache_config=CacheConfig(enabled=False),
                invocation_id="call_test_succ_1",
            )
        )
        assert obs.success

        result_call = None
        for call in mock_publish.call_args_list:
            if call.args[0] == "step.tool_result.record":
                result_call = call
                break

        assert result_call is not None, "step.tool_result.record was not emitted"
        payload = result_call.args[1]
        assert payload.get("ok") is True
        assert payload.get("exit_code") == 0
        assert isinstance(payload.get("latency_ms"), int)
        assert payload.get("latency_ms") >= 0


def test_safe_executor_propagates_true_exit_code_on_nonzero_failure() -> None:
    """Tool failing with non-zero exit_code (e.g. 127 command not found) propagates it accurately."""
    mock_tool = MagicMock(spec=Tool)
    mock_tool.name = "bash"
    mock_tool.validate = MagicMock(return_value=None)
    mock_tool.execute = AsyncMock(
        return_value=Observation(
            observation_id="obs_fail_127",
            success=False,
            payload={"exit_code": 127},
            error="bash: some_cmd: command not found",
            extra={"exit_code": 127},
        )
    )

    with patch("lca.loop.commit.tool_journal.publish_ep_bound") as mock_publish:
        from lca.cognition.body.executor.safe_executor.executor import SimpleSafeExecutor

        executor = SimpleSafeExecutor(
            permission_manifest=ToolPermissionManifest(allowed_tools=["bash"])
        )
        obs = asyncio.run(
            executor.execute(
                mock_tool,
                {"command": "some_cmd"},
                retry_policy=RetryPolicy(max_retries=0),
                cache_config=CacheConfig(enabled=False),
                invocation_id="call_test_fail_127",
            )
        )
        assert not obs.success

        result_call = None
        for call in mock_publish.call_args_list:
            if call.args[0] == "step.tool_result.record":
                result_call = call
                break

        assert result_call is not None, "step.tool_result.record was not emitted"
        payload = result_call.args[1]
        assert payload.get("ok") is False
        assert payload.get("outcome") == "failure"
        assert payload.get("exit_code") == 127
        assert payload.get("invocation_id") == "call_test_fail_127"
