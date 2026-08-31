"""Test helpers for gateway apps that need a scripted LLM resolver.

Production ``create_app`` no longer accepts ``run_port`` / ``bootstrap_factory`` /
``registry`` / ``file_store`` / ``devices`` — those concerns moved to
``app.state`` ownership under the thin factory (ADR-0115). Tests now
drive the lifespan explicitly to inject scripted dependencies after
boot completes, before any request is served.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from lca.harness.profile.lifespan import profile_lifespan
from tests.support.gateway_scripted import ScriptedLLMResolver

if TYPE_CHECKING:
    from starlette.applications import Starlette


def _install_routes(app: Starlette) -> None:
    """Install routes from the booted ctx's gateway_router.

    Production thin factory installs routes inside the default lifespan;
    tests that drive ``profile_lifespan`` directly need to do this themselves.
    """
    ctx = getattr(app.state, "ctx", None)
    if ctx is None:
        return
    try:
        router = ctx.inject("gateway_router")
        router.install(app)
        app.state.gateway_router = router
    except Exception as exc:
        # minimal profile may lack gateway_router; debug-log instead of raise
        import structlog

        structlog.get_logger("tests.support.gateway_app").debug(
            "gateway_router_install_skipped", error=str(exc)
        )


def create_scripted_app(
    registry: Any = None,
    *,
    run_port: Any = None,
    llm_resolver: Any | None = None,
    profile_path: str | None = None,
) -> Starlette:
    """Build a gateway app whose profile lifespan also installs a scripted LLM.

    Each call returns a fresh app with its own boot — no shared state
    across tests. The scripted resolver is installed by a test-only
    lifespan that wraps the production profile lifespan; boot and
    resolver injection both run on Starlette's startup loop, so no
    side-thread hack and no module-level cache pollution.

    ``registry`` / ``run_port`` are accepted as legacy kwargs (no-op)
    so existing call sites don't have to be reworked; production
    create_app dropped these parameters.
    """
    from gateway.app import create_app

    resolver = llm_resolver if llm_resolver is not None else ScriptedLLMResolver()

    @asynccontextmanager
    async def _scripted_lifespan(app: Starlette) -> AsyncIterator[None]:
        async with profile_lifespan(profile_path or "profiles/web-standard.yaml") as state:
            state["ctx"].provide("llm_resolver", resolver)
            app.state.ctx = state["ctx"]
            _install_routes(app)
            yield

    return create_app(
        profile_path=profile_path,
        lifespan=_scripted_lifespan,
    )
