"""HTTP /api/device/* + WS /api/device/ws — LobeHub GatewayClient protocol.

Re-export barrel: historical entry point for the split device routes.
"""

from __future__ import annotations

from lca.plugins.transport.device_hub.routes.routes_http import (
    agent_run,
    device_status,
    download_companion,
    download_runner_bat,
    download_runner_command,
    install_ps1,
    install_sh,
    list_devices,
    pair_code,
    pair_poll,
    pair_preauth,
    pair_verify,
    rpc,
    system_info,
    tool_call,
    upload_files,
)
from lca.plugins.transport.device_hub.routes.routes_ws import connect_device

__all__ = [
    "agent_run",
    "connect_device",
    "device_status",
    "download_companion",
    "download_runner_bat",
    "download_runner_command",
    "install_ps1",
    "install_sh",
    "list_devices",
    "pair_code",
    "pair_poll",
    "pair_preauth",
    "pair_verify",
    "rpc",
    "system_info",
    "tool_call",
    "upload_files",
]
