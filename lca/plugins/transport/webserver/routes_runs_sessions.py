"""Register ``/runs`` + ``/v1/sessions`` route groups (PR-4 routes-runs-sessions + ADR-0163 决策 5).

Declarative :class:`RouteSpec` catalog. All handler implementations live
in ``lca.plugins.transport.webserver.handlers.runs.api.command_endpoints``
and the matching query handlers in
``lca.plugins.transport.webserver.handlers.runs.api.query_endpoints``.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    answer_run,
    cancel_run,
    create_run,
)
from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    get_run,
    get_run_doctor,
    get_run_evidence,
    get_run_profile,
    stream_run_live,
)
from lca.plugins.transport.webserver.route_register import register_routes

ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/runs", create_run, ("POST", "OPTIONS")),
    RouteSpec("/runs/{run_id}", get_run, ("GET",)),
    RouteSpec("/runs/{run_id}/live", stream_run_live, ("GET", "OPTIONS")),
    RouteSpec("/runs/{run_id}/doctor", get_run_doctor, ("GET",)),
    RouteSpec("/runs/{run_id}/profile", get_run_profile, ("GET",)),
    RouteSpec("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, ("GET",)),
    RouteSpec("/runs/{run_id}/cancel", cancel_run, ("POST", "OPTIONS")),
    RouteSpec("/runs/{run_id}/answer", answer_run, ("POST", "OPTIONS")),
)


@plugin(
    id="lca-gateway-routes-runs-sessions",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /runs (8) + /v1/sessions (8) routes.",
    test_suite="tests.lca_plugins.transport.webserver.test_runs_sessions",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-runs-sessions.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_runs_sessions_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca-gateway-routes-runs-sessions",
    )
