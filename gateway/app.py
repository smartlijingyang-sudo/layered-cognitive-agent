"""Gateway web transport — Starlette adapter for a booted kernel context.

This module is a thin factory: it consumes a booted plugin tree and wires
it into a Starlette application.

Per ADR-0115 决定 6: gateway/app.py 不再调 boot_profile()。所有路由由
plugin 树通过 ctx.inject('gateway_router') 注册。本模块只剩 thin factory。
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
        yield state


def create_app(
    profile_path: str | None = None,
    *, gateway_router: Any = None, lifespan: Any = None,
) -> Starlette:
    """Thin factory: Starlette app wired to a kernel lifespan."""
    resolved = profile_path or os.environ.get("LCA_PROFILE") or DEFAULT_PROFILE_PATH
    app = Starlette(routes=[])
    app.state.kernel_profile = resolved
    app.state.gateway_router = gateway_router
    app.router.lifespan_context = (  # type: ignore[assignment]
        lifespan if lifespan is not None else _kernel_lifespan
    )
    return app


# uvicorn gateway.app:create_app --factory 入口
app = create_app()
