"""RouteSpec catalog and plugin assembly for the ``/v1/assistants`` surface.

Keeps the declarative route table and the ``@plugin`` manifest in one place;
handler implementations live in the sibling submodules.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_JOBS,
    ASSISTANT_SKILL_OVERLAY,
)
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
from lca.plugins.transport.webserver.route.register import register_routes
from lca.plugins.transport.webserver.routes_1.routes_assistants.jobs import (
    assistant_job_item,
    assistant_jobs_root,
    fire_assistant_job,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.lobehub import (
    bind_agent,
    import_lobehub_agent,
    register_lobehub,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.profile import (
    assistants_root,
    get_assistant,
    reimport_assistant,
    retire_assistant,
    revise_assistant_profile,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.skills import (
    install_assistant_skill,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    list_standing_files,
    standing_file_dispatcher,
)

ROUTE_SPECS: tuple[RouteSpec, ...] = (
    # Path is shared between POST (create) and GET (list); the
    # :func:`assistants_root` dispatcher handles both methods.
    RouteSpec(
        "/v1/assistants",
        assistants_root,
        ("POST", "GET", "OPTIONS"),
    ),
    # import-lobehub must come before {assistant_id} to avoid path conflict
    RouteSpec(
        "/v1/assistants/import-lobehub",
        import_lobehub_agent,
        ("POST", "OPTIONS"),
    ),
    RouteSpec("/v1/assistants/{assistant_id}", get_assistant, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/assistants/{assistant_id}/profile",
        revise_assistant_profile,
        ("PATCH", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}:reimport",
        reimport_assistant,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/skills:install",
        install_assistant_skill,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/bind-agent",
        bind_agent,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/register-lobehub",
        register_lobehub,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/retire",
        retire_assistant,
        ("POST", "OPTIONS"),
    ),
    # Path is shared between POST (register) and GET (list); the
    # :func:`assistant_jobs_root` dispatcher handles both methods.
    RouteSpec(
        "/v1/assistants/{assistant_id}/jobs",
        assistant_jobs_root,
        ("POST", "GET", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/jobs/{job_id}:fire",
        fire_assistant_job,
        ("POST", "OPTIONS"),
    ),
    # 卡片路径（ADR-0268 §9）：PUT 合并用户改过的字段，DELETE 删除定义。
    RouteSpec(
        "/v1/assistants/{assistant_id}/jobs/{job_id}",
        assistant_job_item,
        ("PUT", "DELETE", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/standing-files",
        list_standing_files,
        ("GET", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/standing-files/{filename}",
        standing_file_dispatcher,
        ("GET", "PUT", "OPTIONS"),
    ),
)


@plugin(
    id="lca.plugins.transport.webserver.routes_1.routes_assistants",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=("Register /v1/assistants CRUD REST surface (ADR-0187 §3 D7 + PR-5). "),
    test_suite="tests.lca_plugins.transport.webserver.test_routes_assistants",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca.plugins.transport.webserver.routes_assistants.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "route_registry",
            ASSISTANT_CATALOG.key,
            ASSISTANT_SKILL_OVERLAY.key,
            ASSISTANT_JOBS.key,
        ),
        emits=("assistant_routes.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Mount the nine ``/v1/assistants`` routes.

    The routes always mount (``route_registry`` is the only required cap).
    Catalog / overlay / jobs lookups happen inside each handler via
    :func:`_catalog_from_request` / :func:`_jobs_from_request` so the plugin
    stays mountable on profiles without the assistant plugins
    (e.g. ``web-standard``).
    """
    del config
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca.plugins.transport.webserver.routes_1.routes_assistants",
    )
