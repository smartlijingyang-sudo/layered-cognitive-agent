"""request_box_help 人闸（ADR-0248 §3.5）测试。"""

import pytest

from lca.contracts.models.core.execution.decision import (
    HITL_TOOL_NAMES,
    requires_human_input,
)
from lca.infrastructure.tools.box.help import RequestBoxHelpTool, build_box_help_tools


@pytest.mark.asyncio
async def test_request_box_help_returns_approval_request() -> None:
    obs = await RequestBoxHelpTool().execute(
        {"request": "需要输入 2FA 验证码", "context": "SSO 登录"}
    )
    assert obs.success is False
    assert obs.error == "waiting for human approval"
    approval = obs.extra["approval_request"]
    assert approval["type"] == "request_box_help"
    assert approval["request"] == "需要输入 2FA 验证码"
    assert approval["context"] == "SSO 登录"


@pytest.mark.asyncio
async def test_request_box_help_validation() -> None:
    obs = await RequestBoxHelpTool().execute({})
    assert obs.success is False
    assert "request 必填" in obs.error


def test_request_box_help_is_hitl_tool() -> None:
    from types import SimpleNamespace

    assert "request_box_help" in HITL_TOOL_NAMES
    assert requires_human_input([SimpleNamespace(tool_name="request_box_help")]) is True


def test_build_box_help_tools() -> None:
    tools = build_box_help_tools()
    assert [t.name for t in tools] == ["request_box_help"]
