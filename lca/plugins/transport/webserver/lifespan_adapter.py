"""Starlette lifespan adapter — bridge :func:`lca_kernel.run_kernel_lifespan` to Starlette.

本模块提供 :func:`create_app_with_lifespan` factory,负责:

1. 构造一个空 ``Starlette`` 应用
2. 装载 :func:`lca_kernel.run_kernel_lifespan` 异步上下文管理器作为 lifespan
3. lifespan startup 时,从 booted ctx 注入 ``gateway_router``,调用
   :meth:`GatewayRouter.install` 把注册好的路由一次性 append 到 ``app.router.routes``

transport 只 import :mod:`lca_kernel` 公共面(``run_kernel_lifespan``),不 import
任何 kernel 内部模块(``source / resolve / boot / lifecycle / ...``),通过
lint-imports 强制(ADR-0115 决定 3)。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from starlette.applications import Starlette

DEFAULT_PROFILE = "profiles/web-standard.yaml"


def create_app_with_lifespan(
    profile_path: str | None = None,
    *,
    profiles_dir: str | None = None,
) -> Starlette:
    """Create a Starlette app whose lifespan boots the kernel.

    Parameters
    ----------
    profile_path:
        Profile YAML path;默认 ``$LCA_PROFILE`` 跟 ``profiles/web-standard.yaml``。
    profiles_dir:
        解析 profile 时的工作目录;默认 ``.``。

    Returns
    -------
    Starlette
        应用实例;routes 通过 ``gateway_router.register_http()`` 注入,在
        lifespan startup 时一次性 ``install(app)`` 到 ``app.router.routes``。
    """
    profile = profile_path or os.environ.get("LCA_PROFILE") or DEFAULT_PROFILE
    profiles_dir = str(profiles_dir) if profiles_dir else "."
    app = Starlette(routes=[])

    async def _lifespan(scope: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Starlette lifespan protocol;delegates to kernel.run_kernel_lifespan."""
        from lca_kernel import run_kernel_lifespan

        async with run_kernel_lifespan(profiles_dir, profile) as state:
            ctx = state["ctx"]
            router = ctx.inject("gateway_router")
            router.install(app)
            yield {"ctx": ctx}

    app.router.lifespan_context = _lifespan  # type: ignore[assignment]
    return app


__all__ = ["DEFAULT_PROFILE", "create_app_with_lifespan"]
