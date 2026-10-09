"""Starlette lifespan 工厂 — lca-web-server plugin 和 lca_kernel/cli 共用。

ADR-0119 决定 3 + 决定 4:lca-web-server plugin 装 Starlette app,
但 Starlette lifespan 协议(测试 + uvicorn 都需要)由本模块提供,被两边
共用,避免"plugin 知道 cli"或"cli 知道 plugin"的循环依赖。

为什么单独成模块
----------------
- plugin 装 app + 装 state + 装 routes(对 ctx 注入无副作用)
- cli 触发 uvicorn 监听 + SIGTERM 守护(进程级)
- lifespan 是 ASGI 协议层,既被 plugin 用(初始化 app.state)也被 cli 用(serve 时)
- 单独成模块 + 不依赖任何 plugin/cli 实现细节,长期可维护

用法
----
```python
from lca_kernel.boot.lifespan import make_lifespan

# plugin setup 内
app.router.lifespan_context = make_lifespan(ctx)

# 测试用
async with app.router.lifespan_context(app) as state:
    assert state["ctx"] is ctx
```

Lifespan 协议要点
----------------
Starlette 的 ``Router.lifespan_context`` 期望 ``Callable[[App], Generator[Any, Any, Any]]``
(同步 generator function)。本模块用 ``@asynccontextmanager`` 自动包装
async generator 成同步 generator-yielding context manager,符合 Starlette 期望
的形式。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from typing import Any, cast


def make_lifespan(
    ctx: Any,
) -> Callable[[Any], Generator[Any, Any, Any]]:
    """返回一个 Starlette lifespan(同步 generator function)yield ``{"ctx": ctx}``。

    Starlette lifespan 协议:同步 generator function,接受 app 实例,先 startup
    阶段,后 shutdown 阶段。本实现只做协议本身的事,不构造任何业务对象:

    - startup:把 ``ctx`` 写到 ``app.state.ctx``(handler 通过
      ``request.app.state.ctx`` 读)——lifespan 协议本身就是"在 startup
      暴露状态给 handler";我们暴露的是 plugin 树 boot 出来的 cordis
      Context。
    - shutdown:按 LIFO dispose ``app.state``:先停掉 plugin setup 阶段挂载的
      ``app.state.cron_daemon``(若有),再清空 ``app.state.ctx``。

    常驻 Cron 调度守护(ADR-0268)的**启停组合**不属于 lifespan 协议:它由
    webserver plugin setup 的命名步骤
    ``lca.plugins.transport.webserver.server.server.start_cron_daemon``
    负责(构造 + ``start()`` + 挂载到 ``app.state.cron_daemon``);本函数在
    shutdown 时只负责把它停掉。

    返回类型:``Callable[[Any], Generator[Any, Any, Any]]``(同步 generator)
    而非 async context manager,这是 Starlette 要求的 lifespan 协议形式。
    ``@asynccontextmanager`` 装饰的内部函数自动把 async generator 转成
    同步 generator-yielding context manager。

    长期可维护:本函数是 lifespan **协议实现**,不是 hack。
    """

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[dict[str, Any]]:
        # Startup: 装 ctx 到 app.state(handler 通过 request.app.state.ctx 读)
        app.state.ctx = ctx
        try:
            yield {"ctx": ctx}
        finally:
            # Shutdown: LIFO dispose —— 先停 plugin 挂载的 cron 守护(若有),
            # 再清空 ctx。getattr 是 Starlette state 的惯用法:直接用
            # make_lifespan 而不经过 webserver plugin setup 的调用方
            # (cli/test)不会挂载 cron_daemon。
            cron_daemon = getattr(app.state, "cron_daemon", None)
            if cron_daemon is not None:
                await cron_daemon.stop()
            app.state.ctx = None

    # @asynccontextmanager 把 async function 转成 sync context manager;
    # Starlette 期望 sync generator function,运行时与 cast 标注一致。
    return cast("Callable[[Any], Generator[Any, Any, Any]]", _lifespan)


__all__ = ["make_lifespan"]
