"""INV-01: Tool invocation_id lifecycle consistency tests.

Validates that:
1. ToolCall.call_id is non-empty and cast at dispatch.
2. The exact same invocation_id is passed through SafeExecutor to record_step_tool_call,
   commit_body_tool_execute_start/end, and record_step_tool_result.
3. No empty strings or decision_id overrides are used for the tool invocation identity.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from lca.contracts.models.core.execution.decision import Observation, ToolCall
from lca.contracts.protocols.runtime.infra.infra import Tool


def test_tool_call_invocation_id_lifecycle_invariant() -> None:
    """Invocation ID must be non-empty and preserved throughout execution."""
    call_id = "toolu_test_lifecycle_9999"
    tc = ToolCall(call_id=call_id, tool_name="bash", arguments={"command": "echo hi"})
    assert tc.call_id == call_id

    mock_tool = MagicMock(spec=Tool)
    mock_tool.name = "bash"
    mock_tool.validate = MagicMock(return_value=None)
    mock_tool.execute = AsyncMock(
        return_value=Observation(observation_id="obs_1", success=True, payload="hi")
    )

    with patch("lca.loop.commit.tool_journal.publish_ep_bound") as mock_publish:
        from lca.cognition.body.executor.safe_executor.executor import SimpleSafeExecutor
        from lca.contracts.models.team.role.team import (
            CacheConfig,
            RetryPolicy,
            ToolPermissionManifest,
        )

        executor = SimpleSafeExecutor(
            permission_manifest=ToolPermissionManifest(allowed_tools=["bash"])
        )
        obs = asyncio.run(
            executor.execute(
                mock_tool,
                tc.arguments,
                retry_policy=RetryPolicy(max_retries=0),
                cache_config=CacheConfig(enabled=False),
                invocation_id=tc.call_id,
            )
        )
        assert obs.success

        # Inspect all events emitted to fact gateway
        emitted_calls = mock_publish.call_args_list
        eps_emitted = [call.args[0] for call in emitted_calls]

        assert "step.tool_call.record" in eps_emitted
        assert "step.tool_result.record" in eps_emitted

        for call in emitted_calls:
            ep = call.args[0]
            payload = call.args[1]
            if ep in (
                "step.tool_call.record",
                "step.tool_result.record",
                "body.tool.execute.start",
                "body.tool.execute.end",
            ):
                assert payload.get("invocation_id") == call_id, (
                    f"Event {ep} had mismatched invocation_id: {payload.get('invocation_id')} != {call_id}"
                )
