"""Webserver transport factory — Starlette + kernel lifespan (ADR-0115).

Thin factory(≤ 60 行,ADR-0115 决定 6):只做"暴露 ``create_app()`` 让
uvicorn 装载"。Lifespan 是 ``@asynccontextmanager`` 形式直接驱动
:func:`lca_kernel.run_kernel_lifespan`,然后从 ctx inject ``gateway_router``
挂路由 + 调 :func:`gateway.bootstrap.install_gateway_state` 装 transport
自己的 ASGI 状态。Starlette 内部把 lifespan wrap 成 ASGI 协议(0.27+)。

职责切割:
- kernel 公共面(:mod:`lca_kernel`)只做 boot + lifecycle,不知道有 Starlette。
- transport factory(:mod:`gateway.app`)把 kernel 桥到 webserver。
- bootstrap glue(:mod:`gateway.bootstrap`)装 transport 自己的 ASGI state。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette

DEFAULT_PROFILE_PATH = "profiles/web-standard.yaml"


@asynccontextmanager
async def _lifespan(app: Starlette):
    """Drive the kernel; install router + bootstrap; yield state.

    Starlette calls this with ``(app)`` as a one-arg context manager and
    converts it to the ASGI lifespan protocol on its own.
    """
    from lca_kernel import run_kernel_lifespan

    profile_path: str = app.state.kernel_profile
    async with run_kernel_lifespan(profile_path) as state:
        ctx = state["ctx"]
        app.state.ctx = ctx
        try:
            router = ctx.inject("gateway_router")
            router.install(app)
            app.state.gateway_router = router
        except KeyError:
            # Minimal profiles may not register ``lca-gateway-router``;
            # the lifespan still completes cleanly.
            pass
        from gateway.bootstrap import install_gateway_state

        install_gateway_state(app, ctx)
        yield state


def create_app(profile_path: str | None = None) -> Starlette:
    """Construct a Starlette app wired to the kernel lifespan."""
    resolved = profile_path or os.environ.get("LCA_PROFILE") or DEFAULT_PROFILE_PATH
    app = Starlette(routes=[])
    app.state.kernel_profile = resolved
    app.router.lifespan_context = _lifespan  # type: ignore[assignment]
    return app


app = create_app()
