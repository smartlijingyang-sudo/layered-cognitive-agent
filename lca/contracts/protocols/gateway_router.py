"""LcaGatewayRouter Protocol — 注册/反注册路由表的唯一入口(ADR-0112 修订版)。

注意: 本 Protocol 与 ADR-0119 决定 4 的 "kernel serve" LCA 后台进程
**无关**。它是 webserver transport 层的 HTTP/WebSocket route registry,
负责把 plugin 注册的 Starlette ``Route`` 列表装到 ``app.router.routes``。
命名历史: 在 LCA 进程切到 ``lca_kernel serve`` 之前, ":8765" 上的
Starlette 应用叫 "gateway",这套路由 API 也跟着叫 "GatewayRouter"。
命名沿用至今以避免 plugin manifest capability 槽位破坏
(``provides=("gateway_router",)`` / ``requires=("gateway_router",)``,
4 个 routes plugin + 1 个 server plugin 全部依赖此 key)。

完整命名空间历史映射看
``docs/adr/0119-followup-gateway-name-map.md``。

Public surface
--------------
- register_http(route: Route) -> Callable[[], None]   # 返回 disposer
- register_websocket(route: WebSocketRoute) -> Callable[[], None]
- set_fallback(handler: Callable) -> Callable[[], None]
- install(app: Starlette) -> None  # lifespan startup 时调用

Why a dedicated module
----------------------
借鉴 deepseek host/webserver/src/index.ts::WebServer.register()。
LCA 的 transport layer 通过此 Protocol 跟 kernel 解耦:

- transport 不直接 import starlette Route 实例(只通过 Protocol)
- plugin 通过 register_http() 注册,register_* 必须返回 disposer
- 调用方必须 ctx.effect(disposer, label=...) 否则 UndeclaredInteractionError

引用 ADR-0112 修订版决定 1 / 决定 3。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute


class LcaGatewayRouter(Protocol):
    """Starlette-based HTTP / WebSocket route registry.

    Routes plugin 通过 ``register_http`` / ``register_websocket`` / ``set_fallback``
    把自己拥有的 Route 推入 router;router 在 ``install(app)`` 时一次性 append 到
    Starlette ``app.router.routes``。每个 ``register_*`` 返回一个 ``() -> None``
    disposer,plugin 必须把它交给 ``ctx.effect(dispose, label=...)`` 让 kernel 收口。
    """

    def register_http(self, route: Route) -> Callable[[], None]:
        """Register one HTTP route. Returns disposer (call ctx.effect on it)."""
        ...

    def register_websocket(self, route: WebSocketRoute) -> Callable[[], None]:
        """Register one WebSocket route. Returns disposer."""
        ...

    def set_fallback(self, handler: Callable[..., object]) -> Callable[[], None]:
        """Claim the fallback seat (one owner only). Returns disposer."""
        ...

    def install(self, app: Starlette) -> None:
        """Install all routes into a Starlette app (lifespan startup)."""
        ...
