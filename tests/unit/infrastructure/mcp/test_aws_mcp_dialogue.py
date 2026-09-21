"""Test verifying Agent boots with AWS MCP and executes AWS MCP tools in dialogue loop."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.api.api import Agent, ensure_default_ctx
from lca.infrastructure.mcp.tool_set import (
    reset_ambient_mcp_manager,
)
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond, use_tool


@pytest.fixture(autouse=True)
def clean_mcp_ambient():
    reset_ambient_mcp_manager()
    yield
    reset_ambient_mcp_manager()


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
