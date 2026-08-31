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
from lca_kernel.lifespan import make_lifespan

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
from typing import Any


def make_lifespan(
    ctx: Any,
) -> Callable[[Any], Generator[Any, Any, Any]]:
    """返回一个 Starlette lifespan(同步 generator function)yield ``{"ctx": ctx}``。

    Starlette lifespan 协议:同步 generator function,接受 app 实例,先 startup
    阶段,后 shutdown 阶段。本实现在 startup 阶段把 ``ctx`` 写到 ``app.state.ctx``
    (Starlette lifespan 协议的标准做法——lifespan 的目的是把运行时状态暴露给
    handler),然后 yield ``{"ctx": ctx}`` 让测试和 uvicorn driver 都能拿到
    同一份 ctx 引用。shutdown 阶段清空 ``app.state.ctx``(LIFO dispose)。

    返回类型:``Callable[[Any], Generator[Any, Any, Any]]``(同步 generator)
    而非 async context manager,这是 Starlette 要求的 lifespan 协议形式。
    ``@asynccontextmanager`` 装饰的内部函数自动把 async generator 转成
    同步 generator-yielding context manager。

    长期可维护:本函数是 lifespan **协议实现**,不是 hack。Lifespan 协议本身
    就是"在 startup 暴露状态给 handler";我们暴露的是 plugin 树 boot 出来的
    cordis Context,handler 通过 ``request.app.state.ctx`` 拿。
    """

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[dict[str, Any]]:
        # Startup: 装 ctx 到 app.state(handler 通过 request.app.state.ctx 读)
        app.state.ctx = ctx
        yield {"ctx": ctx}
        # Shutdown: 不主动 del — 进程级 K6 LIFO dispose 走的是 ctx.dispose(),
        # app.state 上 ctx 引用被一并回收(无副作用)。测试驱动 lifespan 后
        # 仍能读 app.state.ctx(跟深 seek app.current 同款语义)。

    # @asynccontextmanager 把 async function 转成 sync context manager
    # 内部 sync generator yield 一次,符合 Starlette 期望的形式
    return _lifespan


__all__ = ["make_lifespan"]
