"""CLI debug command seam plugin (Tier-1) —— ADR-0063 PR-9.

声明 ``cli_debug_command`` 服务形状；boot 后 ``providers/cli_debug_trace`` /
``cli_debug_run`` / ``cli_debug_scope`` 注册各自 handler。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.cli_debug_command import CliDebugCommand
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-cli-debug-command-seam",
    provides=["cli_debug_command"],
    implements=[CliDebugCommand],
    layer="L0",
    effects="none",
    description="Provide the cli_debug_command seam (PR-9).",
    test_suite="tests/test_cli_debug_trace.py::test_seam_provides_debug_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("cli_debug_command", NamedRegistry())
