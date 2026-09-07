"""Mount the LcaAgentGateway WebSocket route on the production Starlette app."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    make_production_ws_handler,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)


@plugin(
    id="lca-gateway-ws-mount",
    provides=(),
    requires=("web_server",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Mount /v1/runs/{run_id}/ws WebSocket on the LCA webserver app.",
    test_suite="tests.lca_plugins.transport.webserver.test_gateway_ws_mount",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-ws-mount.mounted",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("web_server",),
        emits=("lca_gateway_ws.mounted",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    handle = ctx.require("web_server")
    mount_ws_route(handle.app, handler=make_production_ws_handler())


__all__: tuple[str, ...] = ()
