"""Register ``/v1/assistants`` REST surface (ADR-0187 §3 D7 + PR-5).

Declarative :class:`RouteSpec` catalog with six endpoints that mirror the
``AssistantCatalog`` / ``AssistantSkillOverlay`` protocols (PR-2). Handler
bodies intentionally short-circuit with HTTP 501 + ``COMPAT`` markers until
the catalog plugin (``lca.plugins.assistant.catalog``, PR-3) lands and the
``assistant.catalog`` capability is populated by a real implementation.

Capability contract:

- ``route_registry`` —— required; registration aborts when absent.
- ``assistant.catalog`` / ``assistant.skill_overlay`` —— **not** declared as
  plugin ``requires``; instead each handler consults
  ``request.app.state.assistant_catalog`` (set by the catalog plugin in
  PR-3) and falls back to the 501 envelope when absent. This keeps the
  routes mountable on profiles without the catalog (web-standard today)
  while preserving fail-closed semantics once the catalog lands.

Routes:

- ``POST /v1/assistants`` …… ``catalog.create``
- ``GET  /v1/assistants`` …… ``catalog.list``
- ``GET  /v1/assistants/{assistant_id}`` …… ``catalog.get``
- ``PATCH /v1/assistants/{assistant_id}/profile`` …… ``catalog.revise_profile``
- ``POST /v1/assistants/{assistant_id}/skills:install`` …… ``overlay.install``
- ``POST /v1/assistants/{assistant_id}/retire`` …… ``catalog.retire``

The handler body returns a stable JSON envelope with status code 501 and a
``code="catalog_unavailable"`` field whenever the catalog is missing. The
same envelope is returned for unknown ``assistant_id`` (404) once the
catalog is present; both honour ADR-0187 §3 D7 "fail-closed 4xx, no silent
fallback to default agent".
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_SKILL_OVERLAY
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
from lca.plugins.transport.webserver.handlers.cors import CORS_HEADERS
from lca.plugins.transport.webserver.route_register import register_routes

_ASSISTANT_NOT_IMPLEMENTED_MARKER = (
    "COMPAT(delete-when: assistant.catalog plugin present in resolved profile; "
    "tracking: ADR-0187 PR-3)"
)


def _json(payload: dict[str, Any], *, status_code: int) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _not_implemented(code: str, detail: str = "") -> JSONResponse:
    """Return the stable 501 envelope used while PR-3 catalog lands.

    Handler bodies in this module call this helper until the
    ``assistant.catalog`` capability is bound to a real implementation;
    the marker documents the delete-when condition.
    """
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "type": "not_implemented",
            "marker": _ASSISTANT_NOT_IMPLEMENTED_MARKER,
        }
    }
    if detail:
        payload["error"]["detail"] = detail
    return _json(payload, status_code=501)


def _catalog_from_request(request: Request) -> Any | None:
    """Return the live catalog handle from ``app.state``, else ``None``.

    The catalog plugin (PR-3) installs ``request.app.state.assistant_catalog``;
    until then this returns ``None`` and the handler short-circuits to 501.
    """
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_catalog", None)


def _skill_overlay_from_request(request: Request) -> Any | None:
    """Return the skill-overlay handle from ``app.state`` (PR-6)."""
    state = getattr(request, "app", None)
    if state is None:
        return None
    state_obj = getattr(state, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "assistant_skill_overlay", None)


async def create_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants`` —— ``AssistantCatalog.create`` entry."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.create")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def list_assistants(request: Request) -> JSONResponse:
    """``GET /v1/assistants`` —— ``AssistantCatalog.list``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.list")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def assistants_root(request: Request) -> JSONResponse:
    """``/v1/assistants`` method dispatcher (POST + GET share the path)."""
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await create_assistant(request)
    if method == "GET":
        return await list_assistants(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _not_implemented("catalog_unavailable", f"unsupported method {method!r}")


async def get_assistant(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}`` —— ``AssistantCatalog.get``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.get")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def revise_assistant_profile(request: Request) -> JSONResponse:
    """``PATCH /v1/assistants/{assistant_id}/profile`` —— ``catalog.revise_profile``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.revise_profile")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


async def install_assistant_skill(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/skills:install`` —— ``overlay.install`` (PR-6)."""
    if _skill_overlay_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantSkillOverlay.install")
    return _not_implemented("catalog_pending", "PR-6 overlay handler not wired")


async def retire_assistant(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/retire`` —— ``catalog.retire``."""
    if _catalog_from_request(request) is None:
        return _not_implemented("catalog_unavailable", "AssistantCatalog.retire")
    return _not_implemented("catalog_pending", "PR-3 catalog handler not wired")


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    # Path is shared between POST (create) and GET (list); the
    # :func:`assistants_root` dispatcher handles both methods.
    RouteSpec(
        "/v1/assistants",
        assistants_root,
        ("POST", "GET", "OPTIONS"),
    ),
    RouteSpec("/v1/assistants/{assistant_id}", get_assistant, ("GET", "OPTIONS")),
    RouteSpec(
        "/v1/assistants/{assistant_id}/profile",
        revise_assistant_profile,
        ("PATCH", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/skills:install",
        install_assistant_skill,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/v1/assistants/{assistant_id}/retire",
        retire_assistant,
        ("POST", "OPTIONS"),
    ),
)


@plugin(
    id="lca.plugins.transport.webserver.routes_assistants",
    provides=("webserver.routes.assistants",),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Register /v1/assistants CRUD REST surface (ADR-0187 §3 D7 + PR-5). "
        "Handler bodies short-circuit with HTTP 501 + COMPAT marker until "
        "lca.plugins.assistant.catalog (PR-3) binds assistant.catalog."
    ),
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
        ),
        emits=("assistant_routes.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Mount the six ``/v1/assistants`` routes.

    The routes always mount (``route_registry`` is the only required cap).
    Catalog / overlay lookups happen inside each handler via
    :func:`_catalog_from_request` so the plugin stays mountable on
    profiles without the catalog (e.g. ``web-standard``).
    """
    del config
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        ROUTE_SPECS,
        plugin_id="lca.plugins.transport.webserver.routes_assistants",
    )


__all__ = [
    "ROUTE_SPECS",
    "assistants_root",
    "create_assistant",
    "get_assistant",
    "install_assistant_skill",
    "list_assistants",
    "retire_assistant",
    "revise_assistant_profile",
    "setup",
]
