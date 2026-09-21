"""Tests verifying that Agent boots with MCP tools, injects them into its spec,
and can successfully invoke them.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.application.api.api import Agent
from lca.application.api.spawn import _format_tools_xml
from lca.infrastructure.mcp.tool_set import (
    build_ambient_mcp_tools,
    reset_ambient_mcp_manager,
)


@pytest.fixture(autouse=True)
def clean_mcp_ambient():
    reset_ambient_mcp_manager()
    yield
    reset_ambient_mcp_manager()


@pytest.fixture
def mock_llm():
    """Mock LLM adapter that responds with JSON decision."""
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value='{"action_type":"respond","response_text":"MCP Search complete","rationale":"Done","confidence":1.0}'
    )
    return llm


def test_agent_boot_auto_mcp_injection(mock_llm):
    """Test that Agent(auto_mcp=True) automatically injects configured MCP tools."""
    agent = Agent(
        role="SearchResearcher",
        goal="Gather real-time data using MCP search tools",
        backstory="An AI agent with access to external MCP servers",
        auto_mcp=True,
        llm=mock_llm,
    )

    # 1. Verify tools are injected into AgentSpec
    tool_names = [t.name for t in agent.spec.tools]
    assert len(tool_names) >= 2, f"Expected at least 2 MCP tools, got {tool_names}"
    assert any("searxng" in name for name in tool_names), f"searxng not in {tool_names}"
    assert any("exa" in name for name in tool_names), f"exa not in {tool_names}"

    # 2. Verify tool permission manifest authorizes all injected tools
    allowed_tools = set(agent.role_profile.tool_permission_manifest.allowed_tools)
    for name in tool_names:
        assert name in allowed_tools, f"Tool {name} missing from allowed_tools manifest"

    # 3. Verify tool XML schema formatting for LLM prompt catalog
    tools_xml = _format_tools_xml(agent.spec.tools)
    assert "<tool" in tools_xml
    assert "searxng" in tools_xml
    assert "exa" in tools_xml


def test_agent_boot_explicit_mcp_injection(mock_llm):
    """Test that Agent(tools=mcp_tools) accepts and registers MCP tools directly."""
    ambient_tools = build_ambient_mcp_tools()
    assert len(ambient_tools) >= 2

    agent = Agent(
        role="ExplicitResearcher",
        goal="Test explicit tool injection",
        backstory="Backstory",
        tools=ambient_tools,
        llm=mock_llm,
    )

    assert len(agent.spec.tools) == len(ambient_tools)
    spec_names = {t.name for t in agent.spec.tools}
    ambient_names = {t.name for t in ambient_tools}
    assert spec_names == ambient_names


@pytest.mark.asyncio
async def test_agent_injected_mcp_tool_execution(mock_llm):
    """Verify that an MCP tool injected into the Agent can actually be executed."""
    agent = Agent(
        role="SearchTester",
        goal="Execute MCP search",
        backstory="Backstory",
        auto_mcp=True,
        llm=mock_llm,
    )

    # Find the searxng tool from the agent's injected tools
    searxng_tool = None
    for t in agent.spec.tools:
        if "searxng" in t.name and "search" in t.name:
            searxng_tool = t
            break

    assert searxng_tool is not None, "SearXNG search tool was not injected into Agent"

    # Execute the tool as the Agent runtime / Body would
    obs = await searxng_tool.execute({"query": "test query from agent"})

    assert obs is not None
    assert obs.success is True
    assert obs.payload is not None
    # Payload contains text response from MCP
    assert isinstance(obs.payload, str)
    assert len(obs.payload) > 0
    assert obs.latency_ms is not None
    assert obs.latency_ms >= 0


@pytest.mark.asyncio
async def test_agent_run_loop_invokes_mcp_tool():
    """Verify that an Agent with auto_mcp=True runs an end-to-end loop executing an MCP tool."""
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        reset_capability_bindings,
        set_capability_bindings,
    )
    from tests.harness.scripted_llm import ScriptedLLMAdapter, respond, use_tool

    token = set_capability_bindings(BindingsViewBuilder())
    try:
        llm = ScriptedLLMAdapter(
            {
                "SearchResearcher": [
                    use_tool("mcp__searxng__searxng_search", {"query": "python async"}),
                    respond("I found the search results about python async!"),
                ]
            },
            default_respond=True,
        )

        from lca.application.api.api import ensure_default_ctx

        scope = await ensure_default_ctx()
        agent = Agent(
            role="SearchResearcher",
            goal="Find info on python async using SearXNG",
            backstory="An AI researcher",
            auto_mcp=True,
            llm=llm,
            max_steps=5,
            scope=scope,
        )

        result = await agent.run("Please search for python async")
        assert result.status == "completed"
        assert result.output is not None
        assert len(result.output) > 0
    finally:
        reset_capability_bindings(token)
