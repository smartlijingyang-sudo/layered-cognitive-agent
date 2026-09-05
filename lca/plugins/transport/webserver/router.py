"""RouteRegistry — Starlette 路由表实现(deepseek WebServer 形态)。

ADR-0112 修订版 + ADR-0115:``lca-webserver-router`` 是 L0 SEAM plugin,
通过 :class:`lca.contracts.protocols.route_registry.RouteRegistryProtocol` Protocol
对外暴露 register / set_fallback / install 四方法。

ADR-0119 followup-2 (2026-08-31): 原类名 ``GatewayRouter`` → ``RouteRegistry``,
plugin id ``lca-gateway-router`` → ``lca-webserver-router``,
capability key ``gateway_router`` → ``route_registry``。重命名遵循
ADR-0106 §4.1 命名宪法("Registry" 是许可后缀, "Gateway" 不是)。
原计划 2026-12-31 前的 alias shim 已在 2026-08-31 移除(详见 setup 注释)。

本类与 ADR-0119 决定 4 的 ``kernel_serve`` LCA 后台进程 **无关**。
它是 webserver transport 层的 HTTP route registry,职责是把 plugin 注册的
Starlette ``Route`` 列表装到 ``app.router.routes``。

借鉴 deepseek ``packages/host/webserver/src/index.ts``:

- mutable class(不用 ``@dataclass(frozen=True) + __setattr__`` 反模式)
- ``register_http`` / ``register_websocket`` / ``set_fallback`` 都返回 ``() -> None``
  disposer,plugin 必须 ``ctx.effect(dispose, label=...)`` 收口
- duplicate path 抛 ``ValueError``(composition-level contract,违反即 misconfiguration)
- ``install(app)`` 在 lifespan startup 时把 ``self._exact`` / ``self._prefixes`` /
  ``self._upgrades`` 一次性 append 到 ``app.router.routes``
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.route_registry import RouteRegistryProtocol
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@plugin(
    id="lca-webserver-router",
    provides=("route_registry",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description="Starlette route registry + lifespan installer (deepseek WebServer 形态).",
    test_suite="tests.lca_plugins.transport.webserver.test_router",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-webserver-router.checked", "lca-webserver-router.served"),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("route_registry.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide ``RouteRegistry`` instance via ``ctx.provide('route_registry', ...)``.

    ADR-0119 followup-2: 旧 capability key ``gateway_router`` 已被全部 plugin /
    bundle 替换为 ``route_registry``;``lca/`` 与 ``tests/`` 内已无残留引用,
    compat shim 提前于 2026-12-31 过期日删除。
    """
    registry = RouteRegistry()
    ctx.provide("route_registry", registry)


class RouteRegistry(RouteRegistryProtocol):
    """Mutable Starlette route registry. ``register_*`` returns disposers.

    Disposers mutate the registry in place;they MUST be handed to
    ``ctx.effect(dispose, label=...)`` so the kernel disposes them when the
    boot unit is torn down. ``install(app)`` consumes a snapshot of all
    currently-registered routes;callers must register before install.
    """

    def __init__(self, _ctx: object | None = None) -> None:
        self._exact: dict[str, Route] = {}
        self._prefixes: dict[str, Route] = {}
        self._upgrades: dict[str, WebSocketRoute] = {}
        self._fallback: Callable[..., object] | None = None
        self._app: Starlette | None = None

    # ── Registration (returns disposer) ─────────────────────

    def register_http(self, route: Route) -> Callable[[], None]:
        """Register one HTTP route. Duplicate path → ValueError."""
        if route.path in self._exact or route.path in self._prefixes:
            raise ValueError(f"webserver: duplicate http route {route.path!r}")
        self._exact[route.path] = route
        if self._app is not None:
            self._app.router.routes.append(route)

        def _dispose() -> None:
            self._exact.pop(route.path, None)
            if self._app is not None:
                self._app.router.routes[:] = [
                    existing
                    for existing in self._app.router.routes
                    if getattr(existing, "path", None) != route.path
                ]

        return _dispose

    def register_websocket(self, route: WebSocketRoute) -> Callable[[], None]:
        """Register one WebSocket route. Duplicate path → ValueError."""
        if route.path in self._upgrades:
            raise ValueError(f"webserver: duplicate upgrade route {route.path!r}")
        self._upgrades[route.path] = route
        if self._app is not None:
            self._app.router.routes.append(route)

        def _dispose() -> None:
            self._upgrades.pop(route.path, None)
            if self._app is not None:
                self._app.router.routes[:] = [
                    existing
                    for existing in self._app.router.routes
                    if getattr(existing, "path", None) != route.path
                ]

        return _dispose

    def set_fallback(self, handler: Callable[..., object]) -> Callable[[], None]:
        """Claim the single fallback seat. Second registration → ValueError."""
        if self._fallback is not None:
            raise ValueError("webserver: fallback already registered")
        self._fallback = handler
        return lambda: setattr(self, "_fallback", None)

    # ── Snapshot ─────────────────────────────────────────────

    def install(self, app: Starlette) -> None:
        """Append every registered route to ``app.router.routes``(lifespan startup).

        Starlette 默认 404 行为不变;``_fallback`` 通过后续 PR 在 gateway/app.py
        内部 wired 到 ``app.add_exception_handler(404, ...)``。本阶段 router 只
        持有 fallback 引用,确保 single-owner 约束在注册期即生效。

        After ``install``, late ``register_*`` calls also append to ``app`` so
        opt-in bundles (e.g. composio-tools) can mount routes after
        ``lca-web-server`` setup.
        """
        self._app = app
        mounted_paths = {getattr(route, "path", None) for route in app.router.routes}
        for route in list(self._exact.values()):
            if route.path not in mounted_paths:
                app.router.routes.append(route)
                mounted_paths.add(route.path)
        for route in list(self._prefixes.values()):
            if route.path not in mounted_paths:
                app.router.routes.append(route)
                mounted_paths.add(route.path)
        for upgrade in list(self._upgrades.values()):
            if upgrade.path not in mounted_paths:
                app.router.routes.append(upgrade)
                mounted_paths.add(upgrade.path)


__all__ = ["RouteRegistry"]
