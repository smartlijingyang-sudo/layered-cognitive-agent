"""webserver 请求级 trace_id 隔离(ADR-0183 §3.9 / PR-12)。

不起真实 webserver(需完整 profile boot);用纯 ASGI TraceIdMiddleware +
真实 EventBus + asyncio.Barrier 强制并发交错,验证两个请求的事件链
trace_id 各自独立、不串、请求退出后 ambient 复位。
"""

from __future__ import annotations

import asyncio

import pytest

from lca.contracts.event import Category, EventPayload
from lca.plugins.events.publishers.delegation_cache.plugin import (
    DelegationCachePlugin,
)
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca.plugins.transport.webserver.lifespan_adapter import TraceIdMiddleware
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import (
    EventBus,
    current_trace_id,
    reset_trace_id,
    set_trace_id,
)
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus[EventPayload]:
    return EventBus(EventRegistry.load(_DEFAULT_CONFIG_DIR))


@pytest.fixture(autouse=True)
def _clean_ambient() -> None:
    from lca_kernel.events import bus as bus_module

    bus_module._current_trace_id.set(None)


async def _drive_request(app: TraceIdMiddleware, path: str) -> None:
    """模拟一次 ASGI http 请求。"""
    scope: dict[str, object] = {"type": "http", "method": "POST", "path": path}

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, object]) -> None:
        return None

    await app(scope, receive, send)


class TestWebserverTraceIsolation:
    async def test_two_concurrent_requests_isolated_traces(
        self, bus: EventBus[EventPayload]
    ) -> None:
        """并发两请求:各自事件链 trace_id 独立,互不串。"""
        records: dict[str, tuple[str, str | None]] = {}
        subscriber_seen: list[str] = []
        barrier = asyncio.Barrier(2)

        bus.subscribe(
            plugin=ConsoleProjectorSubscriber,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, r: subscriber_seen.append(r.trace_id),
        )

        async def inner_app(scope: dict[str, object], receive, send) -> None:
            await barrier.wait()  # 强制两请求在对方上下文存活期间交错
            payload = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
            ref = bus.publish(payload, producer=DelegationCachePlugin)
            records[str(scope["path"])] = (ref.trace_id, current_trace_id())
            await barrier.wait()  # 发布后再次交错,放大串扰窗口

        app = TraceIdMiddleware(inner_app)
        await asyncio.gather(
            _drive_request(app, "/req/a"),
            _drive_request(app, "/req/b"),
        )

        trace_a, ambient_a = records["/req/a"]
        trace_b, ambient_b = records["/req/b"]
        # 各自事件用了自己请求的 ambient trace
        assert trace_a == ambient_a
        assert trace_b == ambient_b
        # 两请求 trace 不同
        assert trace_a != trace_b
        assert trace_a.startswith("trc")
        assert trace_b.startswith("trc")
        # subscriber 见到的事件链恰好是这两个 trace,无第三值
        assert sorted(subscriber_seen) == sorted([trace_a, trace_b])
        # 请求退出后 ambient 复位
        assert current_trace_id() is None

    async def test_outer_ambient_restored_after_request(self, bus: EventBus[EventPayload]) -> None:
        """请求退出用 token reset:外层 ambient 值不被请求覆盖。"""

        async def inner_app(scope: dict[str, object], receive, send) -> None:
            payload = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
            bus.publish(payload, producer=DelegationCachePlugin)

        token = set_trace_id("trc_outer")
        try:
            await _drive_request(TraceIdMiddleware(inner_app), "/req/x")
            assert current_trace_id() == "trc_outer"
        finally:
            reset_trace_id(token)

    async def test_lifespan_scope_not_traced(self) -> None:
        """lifespan scope 不承载请求,不注入 trace。"""
        seen: list[str | None] = []

        async def inner_app(scope: dict[str, object], receive, send) -> None:
            seen.append(current_trace_id())

        async def receive() -> dict[str, object]:
            return {}

        async def send(message: dict[str, object]) -> None:
            return None

        app = TraceIdMiddleware(inner_app)
        await app({"type": "lifespan"}, receive, send)
        assert seen == [None]

    async def test_request_exception_still_resets(self) -> None:
        """请求处理抛错也走 finally reset,不泄漏到下一个请求。"""

        async def boom_app(scope: dict[str, object], receive, send) -> None:
            raise RuntimeError("request failed")

        app = TraceIdMiddleware(boom_app)
        with pytest.raises(RuntimeError, match="request failed"):
            await _drive_request(app, "/req/boom")
        assert current_trace_id() is None
