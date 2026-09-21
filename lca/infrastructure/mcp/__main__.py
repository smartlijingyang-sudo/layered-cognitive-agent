"""CLI entrypoint for MCP diagnostics and management: python -m lca.infrastructure.mcp."""

from __future__ import annotations

import asyncio

from lca.infrastructure.mcp.config import find_mcp_config_path, load_mcp_servers
from lca.infrastructure.mcp.manager import MCPManager


async def _run_doctor() -> None:
    config_path = find_mcp_config_path()
    print("=" * 60)
    print("LCA Model Context Protocol (MCP) Doctor")
    print("=" * 60)

    if not config_path:
        print("✗ No mcp.yaml found. (Looked in ./mcp.yaml, ./.lca/mcp.yaml, ~/.lca/mcp.yaml)")
        print("  Create a dedicated mcp.yaml to configure external MCP servers.")
        return

    print(f"✓ Config file: {config_path}")
    servers = load_mcp_servers(config_path)
    print(f"✓ Configured servers: {list(servers.keys())}\n")

    manager = MCPManager(servers)
    print("Connecting and discovering tools from MCP servers...")
    await manager.initialize()

    report = manager.doctor()
    print(
        f"\nSummary: {report['healthy_servers']} healthy, {report['failed_servers']} failing, {report['total_tools']} tools discovered.\n"
    )

    for name, s_info in report["servers"].items():
        symbol = "✓" if s_info["status"] == "healthy" else "✗"
        print(f"  {symbol} [{name}] ({s_info['transport']}): status = {s_info['status']}")
        if s_info["tools"]:
            print(f"    Tools ({len(s_info['tools'])}): {', '.join(s_info['tools'])}")
        if s_info["last_error"]:
            print(f"    Error: {s_info['last_error']}")

    print("=" * 60)
    await manager.close()


def main() -> None:
    asyncio.run(_run_doctor())


if __name__ == "__main__":
    main()
