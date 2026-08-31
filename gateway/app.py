"""Webserver transport factory — Starlette + kernel lifespan (ADR-0115)。

K0 transport 桥在启动全景中的位置
=================================

K0 启动序列(进程从无到 yield 出 running ctx)
    1. ``create_app()`` 构造 Starlette(routes=[])。
    2. ``app.router.lifespan_context = _lifespan`` —— 把 K6 的
       :func:`run_kernel_lifespan` 注入 ASGI lifespan 协议。
    3. uvicorn 启动进程,触发 ASGI lifespan 协议:
       3.1 ``_lifespan`` → ``run_kernel_lifespan(profile_path)``
       3.2   内层  await run_kernel(...)        ← K1–K5 全部完成
       3.3   内层  install signal/fail-loud     ← K6 钩子
       3.4   内层  yield {"ctx": ctx}
       3.5 本层  ctx.inject("gateway_router").install(app)  ← 挂路由
       3.6 本层  install_gateway_state(app, ctx)            ← 装 transport 资源
       3.7 yield state                                         ← uvicorn 开始 accept

职责切割(ADR-0115 决定 6)
------------------------
- kernel 公共面(:mod:`lca_kernel`)只做 boot + lifecycle,不知道有 Starlette。
- transport factory(:mod:`gateway.app`,本模块)把 kernel 桥到 webserver,
  负责"在 boot 完的 ctx 上挂路由 + 装 transport 自己资源"。
- bootstrap glue(:mod:`gateway.bootstrap`)装 transport 自己的 ASGI state
  (FileStore / DeviceRegistry / DeviceHub)。

Thin factory 约束
----------------
本文件 ≤ 60 行(ADR-0115 决定 6)。任何 webserver 配置、CORS、middleware
都不写在这里,而是放在 ``gateway.bootstrap`` 或 routes 插件里。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette

DEFAULT_PROFILE_PATH = "profiles/web-standard.yaml"


@asynccontextmanager
async def _lifespan(app: Starlette):
    """ASGI lifespan 协议实现:把 K0 桥到 K3+K6。

    Starlette calls this with ``(app)`` as a one-arg context manager and
    converts it to the ASGI lifespan protocol on its own.

    流程(对应模块 docstring 的 3.x 步):
        3.2 调 ``run_kernel_lifespan`` —— K1–K5 全部完成 + K6 钩子装好
        3.5 ``ctx.inject("gateway_router").install(app)`` —— 挂 routes
        3.6 ``install_gateway_state(app, ctx)`` —— 装 transport 资源
        3.7 yield state —— uvicorn 进入 accept

    完整 K 链路地图见模块 docstring 的 3.x 步。
    """
    from lca_kernel import run_kernel_lifespan  # ↓ K6:从 K6 拿 K0→K3→K6 联合入口

    profile_path: str = (
        app.state.kernel_profile
    )  # ↑ K0:从 ASGI state 取 profile path(create_app 注入)
    async with run_kernel_lifespan(
        profile_path
    ) as state:  # ↓ K6:进入 K6 入口;内层跑 K1–K5 + K6 钩子
        ctx = state["ctx"]  # ↑ K6:从 yield 出来的字典拿 booted cordis.Context
        app.state.ctx = ctx  # ↑ K0:把 ctx 挂到 ASGI state 供 handler 用
        try:
            router = ctx.inject(
                "gateway_router"
            )  # ↑ K3:从 ctx 拿 lca-gateway-router 插件 provide 的实例
            router.install(app)  # ↓ K0:把 routes 插件攒的 Route 列表 append 到 app.router.routes
            app.state.gateway_router = router  # ↑ K0:也存一份到 ASGI state
        except KeyError:
            # Minimal profiles may not register ``lca-gateway-router``;
            # the lifespan still completes cleanly.
            pass  # 防御性:无 router 时 lifespan 仍完成
        from gateway.bootstrap import install_gateway_state  # ↓ K0:bootstrap glue 装 transport 资源

        install_gateway_state(
            app, ctx
        )  # ↓ K0:把 LocalFileStore / DeviceRegistry / DeviceHub 装到 ASGI state
        yield state  # ↓ K6:把控制权交回 ASGI lifespan 协议,uvicorn 开始 accept


def create_app(profile_path: str | None = None) -> Starlette:
    """构造一个绑定到 kernel lifespan 的 Starlette 应用。

    uvicorn 命令形如 ``uvicorn gateway.app:app``;
    profile 可通过 ``LCA_PROFILE`` 环境变量或本参数显式覆盖。
    """
    resolved = (
        profile_path or os.environ.get("LCA_PROFILE") or DEFAULT_PROFILE_PATH
    )  # ↑ K0:三段 fallback(参数 > env > 默认)
    app = Starlette(routes=[])  # ↑ K0:空 routes 容器,routes 由 routes 插件在 lifespan 期间装
    app.state.kernel_profile = resolved  # ↑ K0:把 profile path 存到 ASGI state,供 _lifespan 读
    app.router.lifespan_context = _lifespan  # type: ignore[assignment]              # ↓ K0→K6:把 K6 入口注入 ASGI lifespan 协议
    return app  # ↑ K0:返回 Starlette 给 uvicorn


# ↓ K0:模块级 app 供 ``uvicorn gateway.app:app`` 装载;create_app 内部 _lifespan 会触发 K6 入口
app = create_app()
