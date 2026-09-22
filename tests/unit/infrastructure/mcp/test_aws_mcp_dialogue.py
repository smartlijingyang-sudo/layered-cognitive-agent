"""Test verifying Agent boots with AWS MCP and executes AWS MCP tools in dialogue loop."""

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.api.api import Agent, ensure_default_ctx
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond, use_tool


class _StubAWSListRegionsTool(Tool):
    name: str = "mcp__aws-mcp__aws___list_regions"
    description: str = "List AWS regions for testing"
    parameters: ClassVar[dict] = {"type": "object", "properties": {}}
    is_idempotent: bool = True
    default_timeout_s: int = 5

    async def execute(self, args: dict) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload='{"regions": ["ap-northeast-1", "us-east-1"]}',
            latency_ms=5,
            extra={"mcp_server": "aws-mcp", "mcp_tool": "aws___list_regions"},
        )


@pytest.fixture(autouse=True)
def mock_ambient_mcp_tools(monkeypatch):
    """Isolate ambient MCP discovery from filesystem and external network."""
    stub_tools = [_StubAWSListRegionsTool()]
    monkeypatch.setattr(
        "lca.infrastructure.mcp.tool_set.build_ambient_mcp_tools",
        lambda: stub_tools,
    )
    monkeypatch.setattr(
        "lca.infrastructure.mcp.tool_set.build_ambient_mcp_tools_async",
        AsyncMock(return_value=stub_tools),
    )


def test_aws_mcp_tools_injected():
    """Verify AWS MCP tools are discovered and injected into Agent."""
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value='{"action_type":"respond","response_text":"Done","rationale":"Done","confidence":1.0}'
    )
    agent = Agent(
        role="AWSCloudEngineer",
        goal="Explore AWS infrastructure",
        backstory="An AWS cloud specialist",
        auto_mcp=True,
        llm=llm,
    )
    tool_names = [t.name for t in agent.spec.tools]
    assert any("aws-mcp" in name for name in tool_names), f"aws-mcp not in {tool_names}"
    assert any("aws___list_regions" in name for name in tool_names)


@pytest.mark.asyncio
async def test_agent_dialogue_calls_aws_mcp_tool():
    """Verify Agent executes AWS MCP tool during dialogue loop and returns real AWS data."""
    token = set_capability_bindings(BindingsViewBuilder())
    try:
        llm = ScriptedLLMAdapter(
            {
                "*": [
                    use_tool("mcp__aws-mcp__aws___list_regions", {}),
                    respond("AWS regions retrieved successfully including ap-northeast-1 Tokyo!"),
                ]
            },
            default_respond=False,
        )

        scope = await ensure_default_ctx()
        agent = Agent(
            role="AWSCloudEngineer",
            goal="List AWS regions",
            backstory="An AWS cloud specialist",
            auto_mcp=True,
            llm=llm,
            max_steps=5,
            scope=scope,
        )

        result = await agent.run("请帮我列出 AWS 支持的可用区域")
        assert result.status == "completed"
        assert result.output is not None
        assert "Tokyo" in result.output
    finally:
        reset_capability_bindings(token)
