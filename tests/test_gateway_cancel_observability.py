"""Gateway cancel 路径：Finished 先于 hub.close，无 OTel 跨 Context 泄漏。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import patch

import pytest

from gateway.run_executor import create_run_session, schedule_run
from gateway.run_registry import RunRegistry, RunStatus
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.observability.journal import AgentRunFinished
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.layer3_agent.cognitive_agent import CognitiveAgent


class _HangRuntime:
    async def run(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        await asyncio.Event().wait()


def _role() -> RoleProfile:
    return RoleProfile(
        role="测试员",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


class _HangAgent:
    """execute_run 注入用：走 CognitiveAgent 容器开闭，run 内 hang。"""

    def __init__(self, hub: Any) -> None:
        self._inner = CognitiveAgent(_HangRuntime(), _role(), hub)  # type: ignore[arg-type]

    async def run(self, objective: str) -> Any:
        return await self._inner.run(objective)


@pytest.mark.asyncio
async def test_execute_run_cancel_no_otel_detach_noise(caplog: pytest.LogCaptureFixture) -> None:
    registry = RunRegistry()
    session = create_run_session(registry, question="hang", user_text="hang", mode="solo")

    with patch("gateway.run_executor.build_solo_agent", return_value=_HangAgent(session.hub)):
        task = schedule_run(registry, session)
        await asyncio.sleep(0)
        task.cancel()
        with (
            caplog.at_level(logging.ERROR, logger="opentelemetry.context"),
            pytest.raises(asyncio.CancelledError),
        ):
            await task

    finished = [e for e in session.hub.journal.events if isinstance(e.event, AgentRunFinished)]
    assert len(finished) == 1
    assert finished[0].event.status == TaskStatus.CANCELED.value
    assert session.status == RunStatus.CANCELED
    assert not any("Failed to detach context" in r.message for r in caplog.records)
