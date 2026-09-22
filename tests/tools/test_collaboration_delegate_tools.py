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
    tool = TeamCastTool()
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
    assert "架构三角已形成完全共识" in payload["synthesized_verdict"]
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
