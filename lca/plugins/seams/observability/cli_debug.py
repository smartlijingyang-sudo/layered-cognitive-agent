"""CLI debug command seam plugin (Tier-1) —— ADR-0063 PR-9.

声明 ``cli_debug_command`` 服务形状；boot 后 ``providers/cli_debug_trace`` /
``cli_debug_run`` / ``cli_debug_scope`` 注册各自 handler。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.cli_debug_command import CliDebugCommand
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-cli-debug-command-seam.checked", "lca-cli-debug-command-seam.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("cli_debug_command",),
        emits=("cli_debug_command.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("cli_debug_command", NamedRegistry())
