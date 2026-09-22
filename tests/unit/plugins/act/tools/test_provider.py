from unittest.mock import MagicMock

import pytest

from lca.plugins.act.tools.provider import Config, _g2a_factory, _mcp_factory, setup


@pytest.mark.asyncio
async def test_tools_provider_registers_only_configured_factories():
    """Verify provider does NOT sneakily register mcp when only g2a is configured."""
    ctx = MagicMock()
    tools_seam = MagicMock()
    ctx.require.return_value = tools_seam

    await setup.setup(ctx, Config(factories=["g2a"]))
    assert tools_seam.register_factory.call_count == 1
    tools_seam.register_factory.assert_called_once_with("g2a", _g2a_factory)


@pytest.mark.asyncio
async def test_tools_provider_registers_both_when_configured():
    """Verify provider registers both factories when explicitly configured."""
    ctx = MagicMock()
    tools_seam = MagicMock()
    ctx.require.return_value = tools_seam

    await setup.setup(ctx, Config(factories=["g2a", "mcp"]))
    assert tools_seam.register_factory.call_count == 2
    tools_seam.register_factory.assert_any_call("g2a", _g2a_factory)
    tools_seam.register_factory.assert_any_call("mcp", _mcp_factory)


@pytest.mark.asyncio
async def test_tools_provider_registers_only_mcp_when_configured():
    """Verify provider registers only mcp when only mcp is configured."""
    ctx = MagicMock()
    tools_seam = MagicMock()
    ctx.require.return_value = tools_seam

    await setup.setup(ctx, Config(factories=["mcp"]))
    assert tools_seam.register_factory.call_count == 1
    tools_seam.register_factory.assert_called_once_with("mcp", _mcp_factory)
