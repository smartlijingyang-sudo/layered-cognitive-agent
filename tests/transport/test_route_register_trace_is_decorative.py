"""route_register trace emit 装饰性锁住(ADR-0181+1)。

锁住契约:``_instrument_route_handler`` 包装的 route handler 在
EventBus publish 失败时(UnauthorizedPublishError 等 EventMechanismError
族异常)必须继续返回业务响应,handler 不能 fail。

回归覆盖(2026-09-04 web-standard 500):publisher 授权错位导致每次
HTTP 请求被 trace emit 拖到 500。本测试确保 trace 是装饰,observability
失败不影响请求正确性。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lca.plugins.transport.webserver.route_register import (
    _instrument_route_handler,
    _trace_emit_failures,
    trace_emit_failures,
)
from lca_kernel.events.errors import (
    EventNoSinkError,
    UnauthorizedPublishError,
)


@pytest.fixture(autouse=True)
def _reset_trace_emit_failures() -> None:
    """每个测试前清空 trace_emit_failures 计数,避免测试间状态污染。"""
    _trace_emit_failures.clear()
    yield
    _trace_emit_failures.clear()


class _StubRequest:
    """最小 Starlette Request 替身,只取 method。"""

    def __init__(self, method: str = "GET") -> None:
        self.method = method


def _install_publisher_exception(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    """monkeypatch 掉 ``emit_transport_route_enter`` 让它抛指定异常。

    通过 :mod:`lca.plugins.events.publishers.spine_reflector_transport` 的
    函数级 import 不容易拦截;改直接 patch :mod:`route_register` 内部
    ``_safe_emit`` 用的函数引用。
    """
    from lca.plugins.events.publishers import spine_reflector_transport

    def _enter(**_kwargs: Any) -> None:
        raise exception

    monkeypatch.setattr(spine_reflector_transport, "emit_transport_route_enter", _enter)


def test_async_handler_succeeds_when_enter_trace_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async handler 在 trace enter 抛 UnauthorizedPublishError 时仍返回 200 业务结果。"""

    async def _handler(request: Any) -> dict[str, str]:
        return {"ok": "true"}

    _install_publisher_exception(
        monkeypatch, UnauthorizedPublishError("test", "spine.transport.route.enter")
    )

    wrapped = _instrument_route_handler(_handler, path="/x")
    result = asyncio.run(wrapped(_StubRequest("GET")))
    assert result == {"ok": "true"}
    # 失败计数 +1
    assert trace_emit_failures()["transport.route.enter"] == 1


def test_async_handler_succeeds_when_exit_trace_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async handler 业务成功,但 exit trace 抛 EventNoSinkError → handler 仍 200。"""
    from lca.plugins.events.publishers import spine_reflector_transport

    def _exit(**_kwargs: Any) -> None:
        raise EventNoSinkError("spine.transport.route.exit")

    monkeypatch.setattr(spine_reflector_transport, "emit_transport_route_exit", _exit)

    async def _handler(request: Any) -> dict[str, str]:
        return {"ok": "true"}

    wrapped = _instrument_route_handler(_handler, path="/x")
    result = asyncio.run(wrapped(_StubRequest("GET")))
    assert result == {"ok": "true"}
    assert trace_emit_failures()["transport.route.exit"] == 1


def test_async_handler_propagates_handler_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handler 自身抛 ValueError → 仍上抛,不被 trace 装饰吞掉。"""
    from lca.plugins.events.publishers import spine_reflector_transport

    monkeypatch.setattr(
        spine_reflector_transport,
        "emit_transport_route_exit",
        lambda **_k: (_ for _ in ()).throw(EventNoSinkError("spine.transport.route.exit")),
    )

    async def _handler(request: Any) -> None:
        raise ValueError("business bug")

    wrapped = _instrument_route_handler(_handler, path="/x")
    with pytest.raises(ValueError, match="business bug"):
        asyncio.run(wrapped(_StubRequest("GET")))


def test_async_handler_propagates_non_eventbus_trace_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trace emit 抛非 EventMechanismError 异常(代码 bug)→ 仍上抛。"""
    from lca.plugins.events.publishers import spine_reflector_transport

    def _enter(**_kwargs: Any) -> None:
        raise RuntimeError("code bug, not EventMechanismError")

    monkeypatch.setattr(spine_reflector_transport, "emit_transport_route_enter", _enter)

    async def _handler(request: Any) -> dict[str, str]:
        return {"ok": "true"}

    wrapped = _instrument_route_handler(_handler, path="/x")
    # 必须上抛,不吞掉(违反"trace 装饰性"反而掩盖代码 bug)
    with pytest.raises(RuntimeError, match="code bug"):
        asyncio.run(wrapped(_StubRequest("GET")))
    # 不应被计数(因为不是 EventMechanismError)
    assert "transport.route.enter" not in trace_emit_failures()


def test_sync_handler_succeeds_when_enter_trace_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同步 handler 同样不被 trace 拖死。"""

    def _handler(request: Any) -> dict[str, str]:
        return {"ok": "true"}

    _install_publisher_exception(
        monkeypatch, UnauthorizedPublishError("test", "spine.transport.route.enter")
    )

    wrapped = _instrument_route_handler(_handler, path="/x")
    result = wrapped(_StubRequest("GET"))
    # 同步 handler 直接返回 dict 而非 awaitable
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    assert result == {"ok": "true"}
    assert trace_emit_failures()["transport.route.enter"] == 1
