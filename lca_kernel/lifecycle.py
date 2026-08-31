"""K6:Process 生命周期 + Fail-loud + Shutdown 协调(ADR-0115 K6 + ADR-0117)。

Public surface
--------------
- :data:`FAIL_LOUD_RELEASE_TIMEOUT_MS` —— dispose 必须在 2 秒内完成
  (借鉴 deepseek ``app-boot/src/index.ts:FAIL_LOUD_RELEASE_TIMEOUT_MS``)。
- :class:`ShutdownCoordinator` / :class:`DefaultShutdownCoordinator`。
- :func:`install_fail_loud` / :func:`install_signal_handlers`。
- :func:`create_shutdown_coordinator` / :func:`run_kernel_lifespan`。
"""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from typing import Any, Protocol, runtime_checkable

from lca_kernel.errors import FailLoudError, KernelError

FAIL_LOUD_RELEASE_TIMEOUT_MS: int = 2000


@runtime_checkable
class ShutdownCoordinator(Protocol):
    """协调 process 退出时的多源 dispose 顺序。

    Sources of shutdown:
    1. SIGTERM(supervisor):exit 0
    2. SIGINT(user Ctrl-C):exit 130
    3. unhandledRejection / uncaughtException(bug):exit 1
    4. ctx.appExit()(one-shot runner):exit 0
    """

    @property
    def is_shutting_down(self) -> bool: ...
    async def shutdown(self, code: int) -> None: ...
    def interrupt(self, code: int) -> None: ...
    def register_transport(self, transport: Any, listen_handle: Any) -> Callable[[], None]: ...


class DefaultShutdownCoordinator:
    """默认 ShutdownCoordinator 实现:LIFO 反序 dispose。

    ``is_shutting_down`` 在第一次 :meth:`shutdown` 调用前为 ``False``;
    后续 ``shutdown`` / ``interrupt`` 调用都被去重,以防 SIGTERM +
    unhandledRejection 同时触发时 dispose 两次。
    """

    def __init__(self, kernel: Any) -> None:
        self._kernel = kernel
        self._is_shutting_down = False
        self._last_code: int | None = None
        self._transports: list[tuple[Any, Any]] = []

    @property
    def is_shutting_down(self) -> bool:
        return self._is_shutting_down

    def register_transport(
        self,
        transport: Any,
        listen_handle: Any,
    ) -> Callable[[], None]:
        """注册一个 transport handle;返回 disposer(LIFO dispose 顺序)。"""
        entry = (transport, listen_handle)
        self._transports.append(entry)

        def _unregister() -> None:
            with suppress(ValueError):
                self._transports.remove(entry)

        return _unregister

    def interrupt(self, code: int) -> None:
        """Fire-and-forget 启动 shutdown;不阻塞 signal handler。"""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if not loop.is_closed():
            loop.create_task(self.shutdown(code))

    async def shutdown(self, code: int) -> None:
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        self._last_code = code
        # LIFO dispose: last registered transport closes first.
        for _t, handle in reversed(self._transports):
            with suppress(Exception):
                if handle is not None:
                    handle.close()
        kernel = self._kernel
        if kernel is None:
            sys.exit(code)
        try:
            await asyncio.wait_for(
                kernel.dispose(),
                timeout=FAIL_LOUD_RELEASE_TIMEOUT_MS / 1000,
            )
        except asyncio.TimeoutError:
            pass
        except Exception as exc:
            raise KernelError(f"shutdown failed: {exc}") from exc
        finally:
            sys.exit(code)


def install_fail_loud(coordinator: ShutdownCoordinator) -> None:
    """装 sys.excepthook + asyncio loop handler + threading.excepthook。"""
    if not isinstance(coordinator, DefaultShutdownCoordinator):
        raise TypeError(
            "install_fail_loud expects DefaultShutdownCoordinator",
        )

    def _on_unhandled(exc_type: Any, exc_value: Any, _exc_tb: Any) -> None:
        if coordinator.is_shutting_down:
            return
        coordinator.interrupt(1)
        raise FailLoudError(f"unhandled {exc_type.__name__}: {exc_value}")

    sys.excepthook = _on_unhandled
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.set_exception_handler(
            lambda _l, ctx: _on_unhandled(
                ctx.get("exception_type", Exception),
                ctx.get("exception"),
                None,
            )
        )
    threading.excepthook = lambda args: _on_unhandled(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
    )


def install_signal_handlers(coordinator: ShutdownCoordinator) -> None:
    """装 SIGTERM(0)/ SIGINT(130) handler(仅主线程有效)。"""

    def _on_sigterm(*_: Any) -> None:
        coordinator.interrupt(0)

    def _on_sigint(*_: Any) -> None:
        coordinator.interrupt(130)

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
        signal.signal(signal.SIGINT, _on_sigint)
    except ValueError:
        # Signal handlers can only be installed from the main thread; tests
        # drive shutdown via explicit ``coordinator.shutdown(...)`` calls.
        pass


def create_shutdown_coordinator(kernel: Any) -> DefaultShutdownCoordinator:
    """工厂:返回默认 :class:`DefaultShutdownCoordinator`。"""
    return DefaultShutdownCoordinator(kernel=kernel)


@asynccontextmanager
async def run_kernel_lifespan(_profiles_dir: Any, profile_path: Any) -> Any:
    """AsyncContextManager 桥给 ASGI / stdio lifespan。"""
    from lca_kernel.boot import run_kernel

    ctx = await run_kernel(profile_path)
    coordinator = create_shutdown_coordinator(ctx)
    install_signal_handlers(coordinator)
    install_fail_loud(coordinator)
    try:
        yield {"ctx": ctx}
    finally:
        await coordinator.shutdown(0)


__all__ = [
    "FAIL_LOUD_RELEASE_TIMEOUT_MS",
    "DefaultShutdownCoordinator",
    "ShutdownCoordinator",
    "create_shutdown_coordinator",
    "install_fail_loud",
    "install_signal_handlers",
    "run_kernel_lifespan",
]
