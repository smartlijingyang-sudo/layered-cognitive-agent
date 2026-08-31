"""Gateway web transport — Starlette adapter for a booted kernel context.

Thin factory: installs routes via ``ctx.inject('gateway_router')`` and wires
gateway-side singletons into ``app.state`` (PR-7 bootstrap 修复 / ADR-0115)。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette

DEFAULT_PROFILE_PATH = "profiles/web-standard.yaml"


@asynccontextmanager
async def _kernel_lifespan(app: Starlette) -> Any:
    """Bridge :func:`install_profile_lifespan` to Starlette + install routes."""
    from lca.harness.profile.lifespan import install_profile_lifespan

    inner = install_profile_lifespan(app.state.kernel_profile)
    async with inner(app) as state:
        ctx = state.get("ctx") if isinstance(state, dict) else None
        if ctx is not None:
            app.state.ctx = ctx
            try:
                router = ctx.inject("gateway_router")
                router.install(app)
                app.state.gateway_router = router
            except Exception as exc:  # minimal profile may lack router
                import structlog as _sl

                _sl.get_logger("lca.gateway").debug(
                    "gateway_router_install_skipped", error=str(exc)
                )
            from gateway.bootstrap import install_gateway_state

            install_gateway_state(app, ctx)
        yield state


def create_app(
    profile_path: str | None = None,
    *,
    gateway_router: Any = None,
    lifespan: Any = None,
) -> Starlette:
    """Thin factory: Starlette app wired to a kernel lifespan."""
    resolved = profile_path or os.environ.get("LCA_PROFILE") or DEFAULT_PROFILE_PATH
    app = Starlette(routes=[])
    app.state.kernel_profile = resolved
    app.state.gateway_router = gateway_router
    app.router.lifespan_context = lifespan if lifespan is not None else _kernel_lifespan
    return app


app = create_app()
