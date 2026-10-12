"""set_session 跨 asyncio context 幂等回归测试。

run_b9cf3095caed 中 resume 每次在新 task context 调用 ``set_session``，
ContextVar 幂等检查失效，导致 Session 上累积多个 SpineFileSink observer，
同一 spine 事件被写盘 2/3/4 次（45MB 膨胀、doctor H3 duplicate step）。
"""

from __future__ import annotations

import asyncio

from lca.plugins.events._session_observe import (
    clear_observer_catalog,
    register_as_session_observer,
    set_session,
)
from lca.plugins.session.runtime.bus.facade import as_bus_facade
from lca.session.append import Session

_SINK_MARKER = type("RegressionFakeSink", (), {})


def _observer_count(session: Session) -> int:
    return len(session._observers)


def test_set_session_is_idempotent_across_asyncio_tasks() -> None:
    """不同 task context 中重复 set_session 不重复注册 observer。"""
    clear_observer_catalog()
    session = Session("t-set-session-dup")
    facade = as_bus_facade(session)

    def _fake_cb(payload, ref) -> None:
        return None

    register_as_session_observer(_SINK_MARKER, _fake_cb)

    async def _bind_in_fresh_task() -> int:
        # 每个 asyncio.Task 复制父 context，父 context 中 _CURRENT_SESSION_VAR 为空，
        # 等价于 resume 的 HTTP handler task 第一次见该 Session。
        set_session(facade)
        try:
            return _observer_count(session)
        finally:
            set_session(None)

    async def _main() -> tuple[int, int]:
        first = await asyncio.create_task(_bind_in_fresh_task())
        second = await asyncio.create_task(_bind_in_fresh_task())
        return first, second

    try:
        first, second = asyncio.run(_main())
        assert first == 1, f"首次绑定应有 1 个 observer，实际 {first}"
        assert second == 1, f"跨 context 重复 set_session 泄漏 observer：{second}"
    finally:
        clear_observer_catalog()


def test_set_session_same_context_remains_idempotent() -> None:
    """同一 context 内重复 set_session 仍只注册一次（原行为不回退）。"""
    clear_observer_catalog()
    session = Session("t-set-session-same")
    facade = as_bus_facade(session)

    def _fake_cb(payload, ref) -> None:
        return None

    register_as_session_observer(_SINK_MARKER, _fake_cb)
    try:
        set_session(facade)
        set_session(facade)
        assert _observer_count(session) == 1
    finally:
        set_session(None)
        clear_observer_catalog()
