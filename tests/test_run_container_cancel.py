"""run 容器在 CancelledError 路径必须关闭（ADR-0037 容器必闭）。

CancelledError 继承 BaseException 而非 Exception；若只 catch Exception，
AgentRunStarted/TeamRunStarted 的 OTel ambient attach 不会被 Finished 配对
detach，hub.close 时出现「Token was created in a different Context」。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.observability.journal import AgentRunFinished, TeamRunFinished
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from tests.support.observability_helpers import make_test_bound
from lca.layer0_infra.observability.team_profile import TeamTraceProfile
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.team_handle import TeamHandle


class _HangRuntime:
    async def run(self, *args: Any, **kwargs: Any) -> Result:
        del args, kwargs
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _HangStrategy:
    async def run(self, objective: str) -> Result:
        del objective
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _role() -> RoleProfile:
    return RoleProfile(
        role="测试员",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


@pytest.mark.asyncio
async def test_agent_run_finished_on_cancelled_error() -> None:
    hub = make_test_bound()
    agent = CognitiveAgent(_HangRuntime(), _role(), hub)  # type: ignore[arg-type]
    task = asyncio.create_task(agent.run("任务"))
    await asyncio.sleep(0)  # 让 AgentRunStarted 先落地
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    hub.close()

    finished = [e for e in hub.journal.store.events if isinstance(e.event, AgentRunFinished)]
    assert len(finished) == 1
    assert finished[0].event.status == TaskStatus.CANCELED.value


@pytest.mark.asyncio
async def test_team_run_finished_on_cancelled_error() -> None:
    hub = make_test_bound()
    profile = TeamTraceProfile(
        team_id="team-x",
        strategy_key="lead",
        mandate="board",
        lead_role="Lead",
        member_roles=("A",),
    )
    handle = TeamHandle(
        strategy=_HangStrategy(),  # type: ignore[arg-type]
        profile=profile,
        observability=hub,
        members=(),
        lead=None,
    )
    task = asyncio.create_task(handle.run("目标"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    hub.close()

    finished = [e for e in hub.journal.store.events if isinstance(e.event, TeamRunFinished)]
    assert len(finished) == 1
    assert finished[0].event.status == TaskStatus.CANCELED.value
