"""Test helpers for gateway apps that need a scripted LLM resolver.

Tests drive the lifespan explicitly to inject scripted dependencies after
boot completes, before any request is served. The production
``create_app`` factory is now a pure thin factory (ADR-0115), so this
helper wraps ``create_app`` and replaces the lifespan to add the
resolver injection before yielding.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from lca_kernel import run_kernel_lifespan
from tests.support.gateway_scripted import ScriptedLLMResolver

if TYPE_CHECKING:
    from starlette.applications import Starlette


def _install_routes(app: Starlette) -> None:
    """Install routes from the booted ctx's route_registry."""
    ctx = getattr(app.state, "ctx", None)
    if ctx is None:
        return
    try:
        router = ctx.inject("route_registry")
        router.install(app)
        app.state.route_registry = router
    except Exception as exc:
        import structlog

        structlog.get_logger("tests.support.gateway_app").debug(
            "route_registry_install_skipped", error=str(exc)
        )


def create_scripted_app(
    registry: Any = None,
    *,
    run_port: Any = None,
    llm_resolver: Any | None = None,
    profile_path: str | None = None,
) -> Starlette:
    """Build a gateway app whose lifespan injects a scripted LLM resolver.

    ``registry`` / ``run_port`` are accepted as legacy kwargs (no-op)
    so existing call sites don't have to be reworked; production
    create_app dropped these parameters.
    """
    from lca.plugins.transport.webserver.bootstrap import install_bootstrap_state
    from lca_kernel.cli import create_app

    app = asyncio.run(create_app(profile_path=profile_path))
    resolver = llm_resolver if llm_resolver is not None else ScriptedLLMResolver()

    async def _scripted_lifespan(asgi_scope: dict[str, Any], receive: Any, send: Any) -> None:
        if asgi_scope["type"] != "lifespan":
            return
        try:
            async with run_kernel_lifespan(profile_path or "profiles/web-standard.yaml") as state:
                ctx = state["ctx"]
                ctx.provide("llm_resolver", resolver)
                app.state.ctx = ctx
                ctx.inject("route_registry").install(app)
                install_bootstrap_state(app, ctx)
                await send({"type": "lifespan.startup.complete"})
                await receive()
                await send({"type": "lifespan.shutdown.complete"})
        except Exception as exc:
            await send({"type": "lifespan.startup.failed", "message": str(exc)})

    app.router.lifespan_context = _scripted_lifespan  # type: ignore[assignment]
    return app
