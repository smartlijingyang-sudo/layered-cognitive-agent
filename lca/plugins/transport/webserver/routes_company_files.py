"""Register ``POST /files`` — company file-service upload entry.

Separate from ``lca-gateway-routes-openai-compat-files`` on purpose: that plugin
serves the LobeHub read surface and must stay byte-identical, while this one
owns the only outbound dependency (the company file service) and therefore
declares ``effects="network"``.

Dispatch is by HTTP path, not by caller: both frontends reach the same backend
and the same route table.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

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
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.files.fileservice import (
    FileServiceClient,
    FileServiceSettings,
)
from lca.plugins.transport.webserver.handlers.files.upload import upload_files
from lca.plugins.transport.webserver.route.register import register_routes

PLUGIN_ID = "lca-gateway-routes-company-files"


def _settings_from_config(config: Any) -> FileServiceSettings:
    """Read the resolved profile config; ``{from_env: ...}`` is resolved upstream."""
    data = config if isinstance(config, dict) else {}
    raw_timeout = data.get("timeout_s")
    try:
        timeout_s = float(raw_timeout) if raw_timeout is not None else 120.0
    except (TypeError, ValueError):
        timeout_s = 120.0
    return FileServiceSettings(
        base_url=str(data.get("base_url") or "").strip(),
        app_id=str(data.get("app_id") or "").strip(),
        pwd=str(data.get("pwd") or "").strip(),
        timeout_s=timeout_s,
    )


def make_upload_handler(client: FileServiceClient | None) -> Any:
    """Bind the resolved client into the route handler (no capability added)."""

    async def _handler(request: Request) -> JSONResponse:
        return await upload_files(request, client)

    return _handler


@plugin(
    id=PLUGIN_ID,
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="network",
    description="Register POST /files (company file-service upload).",
    test_suite="tests.lca_plugins.transport.webserver.test_company_file_upload",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-company-files.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_company_files_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    registry = ctx.require("route_registry")
    settings = _settings_from_config(config)
    client = FileServiceClient(settings) if settings.configured else None
    specs: tuple[RouteSpec, ...] = (
        RouteSpec("/files", make_upload_handler(client), ("POST", "OPTIONS")),
    )
    register_routes(registry, ctx, specs, plugin_id=PLUGIN_ID)
