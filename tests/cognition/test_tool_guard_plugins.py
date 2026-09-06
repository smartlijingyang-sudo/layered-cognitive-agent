"""Act-plane tool guard plugin tests (ADR-0197)."""

from __future__ import annotations

import asyncio

import pytest

from lca.cognition.body.guard.service import ToolGuardService
from lca.cognition.body.guard.spill import ToolResultSpillGuard
from lca.cognition.body.guard.timeout import ToolTimeoutGuard, _TOOL_TIMEOUT
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.act.tool.pipeline import ToolDefinition, ToolExecutionContext
from lca.contracts.protocols.runtime.infra.infra import Tool


class _SlowTool(Tool):
    name = "slow"
    description = "slow tool"
    parameters: dict[str, object] = {}
    is_idempotent = True
    default_timeout_s = 1

    async def execute(self, args: dict[str, object]) -> Observation:
        await asyncio.sleep(2)
        return Observation(observation_id=new_id("obs"), success=True, payload="ok")


@pytest.mark.asyncio
async def test_timeout_guard_returns_tool_timeout() -> None:
    service = ToolGuardService()
    service.add(ToolTimeoutGuard(), id="timeout", order=10)
    tool = _SlowTool()

    async def inner() -> Observation:
        return await tool.execute({})

    result = await service.execute_with_guards(tool, {}, inner)
    assert result.success is False
    assert result.extra.get("error_code") == _TOOL_TIMEOUT


def test_spill_guard_truncates_large_payload() -> None:
    guard = ToolResultSpillGuard(max_inline_bytes=1024)
    ctx = ToolExecutionContext(tool_name="t", args={})
    big = "x" * 5000
    obs = Observation(observation_id=new_id("obs"), success=True, payload=big)
    spilled = guard.transform_result(ctx, obs)
    assert spilled.extra.get("spill") is True
    assert len(str(spilled.payload)) < len(big)
