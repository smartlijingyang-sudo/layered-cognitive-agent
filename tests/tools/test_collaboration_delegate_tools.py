"""Tests for collaboration delegate tools (TeamCastTool & HandoffToPeerTool)."""

import pytest

from lca.infrastructure.tools.collaboration.delegate_tool import (
    PEER_HANDOFF_TOOL,
    TEAM_CAST_TOOL,
    HandoffToPeerTool,
    TeamCastTool,
)


@pytest.mark.asyncio
async def test_team_cast_tool_execution():
    from lca.application.collaboration.triage import CoordinatorTriageRouter
    from lca.contracts.models.collaboration.peer import PeerProfile

    # 显式注入三个候选专家，与全局角色库解耦（C8 确定性）
    candidates = [
        PeerProfile(
            peer_id="arch_guanlan",
            name="观澜",
            role="架构评审",
            description="契约与分层边界守护",
            home_namespace="roles/architecture/guanlan",
        ),
        PeerProfile(
            peer_id="arch_hengyue",
            name="衡岳",
            role="状态机核查",
            description="不变量与状态机专家",
            home_namespace="roles/architecture/hengyue",
        ),
        PeerProfile(
            peer_id="arch_jingchuan",
            name="镜川",
            role="反模式审计",
            description="代码质量与架构合规",
            home_namespace="roles/architecture/jingchuan",
        ),
    ]
    router = CoordinatorTriageRouter(candidates=candidates)
    tool = TeamCastTool(router=router)
    assert tool.name == TEAM_CAST_TOOL

    obs = await tool.execute(
        {
            "objective": "重构系统审批流，涉及状态机与边界契约",
            "context_extra": {"component": "approval_engine"},
        }
    )

    assert obs.success is True
    payload = obs.payload
    assert payload["consensus_status"] == "unanimous"
    assert "全员共识已形成" in payload["synthesized_verdict"]
    assert len(payload["member_findings"]) == 3
    assert (
        "arch_guanlan" in payload["member_findings"]
        or "architecture/guanlan" in payload["member_findings"]
    )


@pytest.mark.asyncio
async def test_team_cast_tool_validation():
    tool = TeamCastTool()
    err = tool.validate({})
    assert err is not None
    assert "objective" in err


@pytest.mark.asyncio
async def test_handoff_to_peer_tool_execution():
    tool = HandoffToPeerTool()
    assert tool.name == PEER_HANDOFF_TOOL

    obs = await tool.execute(
        {
            "peer_id": "arch_guanlan",
            "objective": "核查领域模型 extra='forbid' 边界",
        }
    )

    assert obs.success is True
    payload = obs.payload
    assert payload["receiver_id"] == "arch_guanlan"
    assert payload["intent"] == "delegate"
    assert "已成功转交" in payload["status_message"]


@pytest.mark.asyncio
async def test_handoff_to_peer_tool_validation():
    tool = HandoffToPeerTool()
    err = tool.validate({"objective": "test"})
    assert err is not None
    assert "peer_id" in err
