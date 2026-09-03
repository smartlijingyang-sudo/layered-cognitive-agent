"""K6 global exception hook — traceback SSOT capture regression tests.

ADR-2026-09-03 traceback-ssot-hook: K6 ``install_fail_loud`` 三钩子
(``sys.excepthook`` + ``asyncio.set_exception_handler`` +
``threading.excepthook``)必须先归一化异常走 :func:`emit_exception_caught`
再触发 shutdown。任何逃出 ``try/except`` 的未捕获异常都必须留下带
``traceback_text`` 的 ``exception.caught`` spine event。

锁定的失败模式(regression):
1. **simple_body.py:117 回归**:``action_type.value`` 把 str 当 enum
   → AttributeError → 逃出 → manifest 只有 ``session_error`` 一行
   字符串 → 无 sidecar json。
2. **裸吞回归**:`except BaseException: pass` 不带 emit,旧测试只检查
   「不崩」不检查「进了 spine」,新测试必须检查 sidecar 落盘。
3. **递归防护回归**:钩子触发 ``emit_exception_caught`` 内部若抛,
   必须 fallback 不再次进入钩子(否则无限递归)。
"""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from lca_kernel.lifecycle import (
    DefaultShutdownCoordinator,
    install_fail_loud,
)

if TYPE_CHECKING:
    import pytest

# ── 测试基础设施 ──────────────────────────────────────────────────────────


class _FakeKernel:
    """Stand-in for cordis Context."""

    async def dispose(self) -> None:
        return None


@contextmanager
def _installed_fail_loud() -> Iterator[DefaultShutdownCoordinator]:
    """装三钩子,卸载时恢复,避免污染 pytest 全局状态。"""
    coord = DefaultShutdownCoordinator(kernel=_FakeKernel())
    saved_excepthook = sys.excepthook
    saved_threading = threading.excepthook
    install_fail_loud(coord)
    try:
        yield coord
    finally:
        sys.excepthook = saved_excepthook
        threading.excepthook = saved_threading


def _patched_sys_exit():
    """``coordinator.interrupt`` 触发 ``sys.exit`` mock,避免测试退出。"""
    return patch.object(sys, "exit")


# ── 1. sys.excepthook 兜底(同步主线程) ────────────────────────────────


def test_excepthook_captures_attribute_error_into_spine(monkeypatch: pytest.MonkeyPatch) -> None:
    """未捕获的 ``AttributeError`` → ``exception.caught`` event + traceback_text。

    模拟 bug: ``decision.action_type.value`` 把 str 当 enum。
    修复: 全局 ``sys.excepthook`` 把它归一化到 SSOT。
    """
    captured: list[dict[str, Any]] = []

    def fake_emit_exception_caught(record: Any) -> None:
        captured.append(record.asdict())

    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        fake_emit_exception_caught,
        raising=False,
    )

    with _installed_fail_loud(), _patched_sys_exit():
        # 模拟未捕获的 AttributeError(不接 try/except)
        sys.excepthook(
            AttributeError,
            AttributeError("'str' object has no attribute 'value'"),
            None,
        )

    assert len(captured) == 1, "三钩子兜底必须触发 emit_exception_caught"
    record = captured[0]
    assert record["exception_class"] == "AttributeError"
    assert "str" in record["exception_message"]
    assert record.get("traceback_text")
    assert record["boundary"].startswith("lifecycle.fail_loud"), (
        f"boundary 应标识 K6 来源,实得 {record['boundary']!r}"
    )


# ── 2. asyncio.set_exception_handler 兜底 ──────────────────────────────


def test_asyncio_handler_captures_task_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """未 await 的 task 异常 → ``exception.caught`` event。"""
    captured: list[dict[str, Any]] = []

    def fake_emit(record: Any) -> None:
        captured.append(record.asdict())

    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        fake_emit,
        raising=False,
    )

    with _installed_fail_loud():
        # 直接调 set_exception_handler 装的回调——比通过真实 task 调度
        # 更稳(asyncio get_exception_handler 在未触发时返 None)。
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # 重新装(因为 install_fail_loud 在 outer scope 装过,这里覆盖
            # 为可观察的 handler,验证 _on_unhandled 走 SSOT 路径)
            from lca_kernel.lifecycle import install_fail_loud as _install
            coord = DefaultShutdownCoordinator(kernel=_FakeKernel())
            _install(coord)
            # 拿到刚装的 asyncio handler
            handler = loop.get_exception_handler()
            assert handler is not None, "asyncio handler 必须被装上"
            handler(loop, {
                "exception": RuntimeError("async boom"),
                "exception_type": RuntimeError,
                "message": "async boom",
            })
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    assert any("async boom" in r.get("exception_message", "") for r in captured), (
        f"asyncio handler 必须捕获 task 异常,实际捕获: {captured}"
    )


# ── 3. threading.excepthook 兜底 ──────────────────────────────────────


def test_threading_excepthook_captures_thread_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """其他线程未捕获异常 → ``exception.caught`` event。"""
    captured: list[dict[str, Any]] = []

    def fake_emit(record: Any) -> None:
        captured.append(record.asdict())

    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        fake_emit,
        raising=False,
    )

    with _installed_fail_loud(), _patched_sys_exit():
        # 模拟 threading.excepthook 被调用(参数是 threading.ExceptHookArgs)
        class _Args:
            exc_type = ValueError
            exc_value = ValueError("thread boom")
            exc_traceback = None

        threading.excepthook(_Args())  # type: ignore[arg-type]

    assert any(
        "thread boom" in r.get("exception_message", "") for r in captured
    ), f"threading hook 必须捕获线程异常,实际捕获: {captured}"


# ── 4. 递归防护 ─────────────────────────────────────────────────────────


def test_excepthook_recursion_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """``emit_exception_caught`` 自身抛 → fallback structlog,不再次进钩子。"""
    call_count = 0

    def fake_emit(record: Any) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("emit itself broken")

    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        fake_emit,
        raising=False,
    )

    with _installed_fail_loud(), _patched_sys_exit():
        # 第一次触发 → fake_emit 抛 → 必须 fallback,不能再次进入 sys.excepthook
        sys.excepthook(
            AttributeError,
            AttributeError("first"),
            None,
        )

    # 关键: 即便 fake_emit 抛,钩子必须 swallow(不让进程崩)
    # call_count 应被 recursion guard 截停,不超过 2(自己兜底可能再触发一次)
    assert call_count <= 2, (
        f"递归防护失败: fake_emit 被调用 {call_count} 次,预期 ≤2"
    )


# ── 5. 不破坏原 shutdown 行为 ─────────────────────────────────────────


def test_excepthook_still_triggers_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """归一化异常后,原 shutdown 路径仍要走(``coordinator.interrupt(1)``)。"""
    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        lambda r: None,
        raising=False,
    )

    interrupted_codes: list[int] = []

    with _installed_fail_loud() as coord:
        # Mock interrupt 验证被调用,避免 asyncio.get_running_loop() 在
        # 同步测试上下文里静默失败(原 interrupt 依赖 running loop)。
        coord.interrupt = lambda code: interrupted_codes.append(code)  # type: ignore[method-assign]
        sys.excepthook(
            RuntimeError,
            RuntimeError("boom"),
            None,
        )

    assert interrupted_codes == [1], (
        f"shutdown 路径必须仍被触发(interrupt(1) 被调),实得 {interrupted_codes}"
    )


# ── 6. shutting_down 后再触发 → no-op ─────────────────────────────────


def test_excepthook_noop_when_shutting_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """已经 shutting_down → 不要再 emit 也不要再调 interrupt。"""
    captured: list[dict[str, Any]] = []

    def fake_emit(record: Any) -> None:
        captured.append(record.asdict())

    monkeypatch.setattr(
        "lca_kernel.lifecycle.emit_exception_caught",
        fake_emit,
        raising=False,
    )

    with _installed_fail_loud() as coord, _patched_sys_exit():
        coord._is_shutting_down = True  # 直接置标志
        sys.excepthook(
            RuntimeError,
            RuntimeError("late boom"),
            None,
        )

    assert captured == [], "shutting_down 期间钩子必须 no-op,防重复 emit"
