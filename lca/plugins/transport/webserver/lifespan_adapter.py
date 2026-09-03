"""Kernel ↔ Transport 桥:HTTP 请求级 trace_id 注入(ADR-0183 §3.9)。

webserver 请求作用域的 ambient trace_id 接入点:请求进入时
:func:`lca_kernel.events.bus.set_trace_id` 一个新 trace,离开时用
token reset。EventBus.publish 缺显式 trace_id 时回退
到该 ambient 值,同一请求内的事件链共享一个 trace_id;contextvars 按
asyncio Task 复制,并发请求互不串。

接入点:本模块提供纯 ASGI :class:`TraceIdMiddleware` 与
:func:`install_trace_middleware`。Starlette app 装配在
:mod:`lca.plugins.transport.webserver.server`(lca-web-server plugin)
内,`app.add_middleware(TraceIdMiddleware)` 的挂载需在该文件一行接入。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca_kernel.events.bus import reset_trace_id, set_trace_id

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_TRACED_SCOPE_TYPES = frozenset({"http", "websocket"})


class TraceIdMiddleware:
    """纯 ASGI 中间件:每个请求一个独立 ambient trace_id。

    进入 ``set_trace_id(new_id("trc"))``,退出用 token ``reset_trace_id``
    恢复外层上下文。lifespan scope 不承载请求,不注入。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") not in _TRACED_SCOPE_TYPES:
            await self.app(scope, receive, send)
            return
        token = set_trace_id(new_id("trc"))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_trace_id(token)


def install_trace_middleware(app: Any) -> None:
    """把 TraceIdMiddleware 挂到 Starlette app(最先加入 = 最外层)。"""
    app.add_middleware(TraceIdMiddleware)


__all__ = ["TraceIdMiddleware", "install_trace_middleware"]
