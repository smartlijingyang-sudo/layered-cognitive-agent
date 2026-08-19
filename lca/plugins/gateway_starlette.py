"""Gateway starlette plugin — Tier-3 (HTTP carrier)."""
from __future__ import annotations

from cordis import plugin


def _try_inject(ctx, key: str):
    try:
        return ctx.inject(key)
    except KeyError:
        return None


def create_session_router(gateway) -> object:
    """Create a minimal Starlette router for /v1/sessions/* endpoints.

    Thin HTTP carrier — delegates to CommandGateway, no business logic.
    """
    from starlette.responses import JSONResponse
    from starlette.routing import Route, Router

    async def create_session(request):
        body = await request.json()
        from lca.contracts.atoms.ids import new_id
        from lca.contracts.harness.command import SessionCreateCommand

        receipt = await gateway.handle_create_session(
            SessionCreateCommand(
                idempotency_key=str(body.get("idempotency_key") or new_id("idem")),
                profile=str(body.get("profile") or "web-standard"),
                preset=body.get("preset"),
                agent_options=body.get("agent_options"),
            )
        )
        return JSONResponse(receipt.__dict__ if hasattr(receipt, "__dict__") else {"id": str(receipt)})

    return Router(routes=[Route("/v1/sessions", create_session, methods=["POST"])])


@plugin(name="lca-gateway-starlette")
async def setup(ctx, config) -> None:
    """Register the gateway starlette router factory.

    sessions / projections are L4-level services; fall back to None if absent.
    """
    sessions = _try_inject(ctx, "sessions")
    projections = _try_inject(ctx, "projections")

    def factory(gateway):
        return create_session_router(gateway)

    ctx.provide("gateway_starlette_router_factory", factory)
    if sessions is not None:
        ctx.provide("gateway_sessions", sessions)
    if projections is not None:
        ctx.provide("gateway_projections", projections)
