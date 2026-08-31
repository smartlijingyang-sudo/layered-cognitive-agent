"""RouteRegistry Protocol 一致性 + register/dispose 幂等 + duplicate 抛错测试。"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute

from lca.contracts.protocols.route_registry import RouteRegistryProtocol
from lca.plugins.transport.webserver.router import RouteRegistry


def _noop(_request: Any) -> None:
    return None


class TestProtocolConformance:
    """RouteRegistry 满足 Protocol 形态。"""

    def test_satisfies_protocol(self) -> None:
        router: RouteRegistryProtocol = RouteRegistry()
        assert hasattr(router, "register_http")
        assert hasattr(router, "register_websocket")
        assert hasattr(router, "set_fallback")
        assert hasattr(router, "install")

    def test_register_http_returns_disposer(self) -> None:
        router = RouteRegistry()
        dispose = router.register_http(Route("/x", _noop, methods=["GET"]))
        assert callable(dispose)
        dispose()
        assert "/x" not in router._exact

    def test_register_websocket_returns_disposer(self) -> None:
        router = RouteRegistry()
        dispose = router.register_websocket(WebSocketRoute("/ws", _noop))
        assert callable(dispose)
        dispose()
        assert "/ws" not in router._upgrades

    def test_set_fallback_returns_disposer(self) -> None:
        router = RouteRegistry()
        dispose = router.set_fallback(_noop)
        assert callable(dispose)
        assert router._fallback is _noop
        dispose()
        assert router._fallback is None


class TestDuplicateDetection:
    """Duplicate path 注册抛错,composition-level contract。"""

    def test_duplicate_http_raises(self) -> None:
        router = RouteRegistry()
        router.register_http(Route("/dup", _noop, methods=["GET"]))
        with pytest.raises(ValueError, match="duplicate http route"):
            router.register_http(Route("/dup", _noop, methods=["POST"]))

    def test_duplicate_websocket_raises(self) -> None:
        router = RouteRegistry()
        router.register_websocket(WebSocketRoute("/ws", _noop))
        with pytest.raises(ValueError, match="duplicate upgrade route"):
            router.register_websocket(WebSocketRoute("/ws", _noop))

    def test_fallback_double_register_raises(self) -> None:
        router = RouteRegistry()
        router.set_fallback(_noop)
        with pytest.raises(ValueError, match="fallback already registered"):
            router.set_fallback(_noop)


class TestInstall:
    """install(app) 把已注册路由一次性 append 到 app.router.routes。"""

    def test_install_appends_routes(self) -> None:
        router = RouteRegistry()
        router.register_http(Route("/a", _noop, methods=["GET"]))
        router.register_http(Route("/b", _noop, methods=["GET"]))
        router.register_websocket(WebSocketRoute("/ws", _noop))
        app = Starlette()
        before = len(app.router.routes)
        router.install(app)
        after = len(app.router.routes)
        assert after - before == 3

    def test_install_idempotent(self) -> None:
        """两次 install 追加两次;router 不缓存已 install 状态。"""
        router = RouteRegistry()
        router.register_http(Route("/a", _noop, methods=["GET"]))
        app = Starlette()
        router.install(app)
        router.install(app)
        assert len(app.router.routes) == 2

    def test_install_empty_router_noop(self) -> None:
        router = RouteRegistry()
        app = Starlette()
        before = len(app.router.routes)
        router.install(app)
        assert len(app.router.routes) == before


class TestDisposeIdempotency:
    """Disposer 多次调用幂等。"""

    def test_dispose_idempotent(self) -> None:
        router = RouteRegistry()
        dispose = router.register_http(Route("/x", _noop, methods=["GET"]))
        dispose()
        dispose()
        assert "/x" not in router._exact

    def test_fallback_dispose_resets_to_none(self) -> None:
        router = RouteRegistry()
        dispose = router.set_fallback(_noop)
        dispose()
        dispose()
        assert router._fallback is None
