"""K6:Process 生命周期 + Fail-loud + Shutdown 协调(ADR-0115 K6 + ADR-0117)。

K6 在启动全景中的位置
====================

K0 transport 桥  →  K1–K5 boot  →  K6 process 生命周期(本模块)
                                          │
                                          ├─ install_signal_handlers
                                          ├─ install_fail_loud
                                          └─ run_kernel_lifespan(finally: shutdown)

K6 是启动链路的最后一段。它**不参与** cordis Context 内部装配,只负责
把已经 boot 完的进程守住:监听 SIGTERM/SIGINT,捕获未处理异常,在
任何来源触发退出时按 LIFO 反序 dispose 所有 plugin fiber,然后退出
进程。Transport(Starlette / JSON-RPC / stdio)不拥有进程生命周期,
只能 ``await run_kernel_lifespan`` 间接拿到 K6 提供的安全保证。

设计约束(ADR-0115 K6)
---------------------
1. 多源关闭去重:SIGTERM + unhandledRejection 同时触发只 dispose 一次
   (``_is_shutting_down`` 单调标志位)。
2. LIFO dispose 顺序:后注册的 transport 先关,避免上层 transport 关闭后
   下层资源还在引用已关闭句柄。
3. Dispose 超时保护:超过 ``FAIL_LOUD_RELEASE_TIMEOUT_MS`` 不再阻塞进程,
   fail-loud 已被记录。
4. transport 不持有 exit code:``sys.exit(code)`` 永远在 K6 内部完成。

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
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
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
            return  # ↑ K6:多源关闭去重(SIGTERM + unhandledRejection 同时到也只 dispose 一次)
        self._is_shutting_down = True  # ↑ K6:单调标志位,后续 interrupt 全部 no-op
        self._last_code = code
        # LIFO dispose: last registered transport closes first.
        for _t, handle in reversed(
            self._transports
        ):  # ↑ K6:后注册 transport 先关(避免上层关闭后下层还在引用)
            with suppress(Exception):
                if handle is not None:
                    handle.close()
        kernel = self._kernel
        if kernel is None:
            sys.exit(code)  # ↑ K6:无 kernel(测试路径)直接退出
        try:
            await asyncio.wait_for(  # ↑ K6:K3 返回的 cordis Context dispose,2 秒硬超时
                kernel.dispose(),
                timeout=FAIL_LOUD_RELEASE_TIMEOUT_MS / 1000,
            )
        except asyncio.TimeoutError:
            pass  # ↑ K6:dispose 超时不再阻塞进程
        except Exception as exc:
            raise KernelError(f"shutdown failed: {exc}") from exc
        finally:
            sys.exit(code)  # ↑ K6:transport 不持有 exit code,本函数收尾


def install_fail_loud(coordinator: ShutdownCoordinator) -> None:
    """装 sys.excepthook + asyncio loop handler + threading.excepthook。"""
    if not isinstance(coordinator, DefaultShutdownCoordinator):
        raise TypeError(
            "install_fail_loud expects DefaultShutdownCoordinator",
        )

    def _on_unhandled(
        exc_type: Any, exc_value: Any, _exc_tb: Any
    ) -> None:  # ↑ K6:三道异常通道的共享回调
        if coordinator.is_shutting_down:
            return  # ↑ K6:已在关闭中,不再重复触发
        coordinator.interrupt(1)  # ↓ K6:fire-and-forget 触发 shutdown(异步跑)
        raise FailLoudError(
            f"unhandled {exc_type.__name__}: {exc_value}"
        )  # ↑ K6:留下 fail-loud 痕迹

    sys.excepthook = _on_unhandled  # ↓ K6:同步路径异常 → _on_unhandled
    try:
        loop = asyncio.get_running_loop()  # ↑ K6:拿当前事件循环(可能尚未启动)
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.set_exception_handler(  # ↓ K6:asyncio 任务未捕获异常 → _on_unhandled
            lambda _l, ctx: _on_unhandled(
                ctx.get("exception_type", Exception),
                ctx.get("exception"),
                None,
            )
        )
    threading.excepthook = lambda args: _on_unhandled(  # ↓ K6:其他线程异常 → _on_unhandled
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
    )


def install_signal_handlers(coordinator: ShutdownCoordinator) -> None:
    """装 SIGTERM(0)/ SIGINT(130) handler(仅主线程有效)。"""

    def _on_sigterm(*_: Any) -> None:  # ↑ K6:supervisor 重启 / k8s pod 终止 → exit 0
        coordinator.interrupt(0)  # ↓ K6:fire-and-forget 触发 shutdown

    def _on_sigint(*_: Any) -> None:  # ↑ K6:Ctrl-C → exit 130
        coordinator.interrupt(130)  # ↓ K6:fire-and-forget 触发 shutdown

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)  # ↓ K6:装 SIGTERM handler
        signal.signal(signal.SIGINT, _on_sigint)  # ↓ K6:装 SIGINT handler
    except ValueError:
        # Signal handlers can only be installed from the main thread; tests
        # drive shutdown via explicit ``coordinator.shutdown(...)`` calls.
        pass


def create_shutdown_coordinator(kernel: Any) -> DefaultShutdownCoordinator:
    """工厂:返回默认 :class:`DefaultShutdownCoordinator`。"""
    return DefaultShutdownCoordinator(kernel=kernel)


@asynccontextmanager
async def run_kernel_lifespan(
    profile_path: str | Path,
    *,
    bootstrap_file_store: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """K0+K3+K6 联合入口:AsyncContextManager 桥给 ASGI lifespan。

    每个 transport(Starlette / JSON-RPC / stdio)都只调这一个入口。
    流程:

    1. ``await run_kernel(profile_path)`` → K1–K5 全套,产出 ``cordis.Context``。
    2. ``create_shutdown_coordinator(ctx)`` + ``install_signal_handlers`` +
       ``install_fail_loud`` —— 装好 K6 的三道钩子。
    3. ``yield {"ctx": ctx}`` —— ASGI lifespan 进入"运行中"状态,transport
       在此期间可自由 ``ctx.inject(...)`` 拿 plugin 产物。
    4. ``finally: await coordinator.shutdown(0)`` —— lifespan 退出时
       LIFO dispose 全部 fiber,``sys.exit(0)`` 收尾。

    Parameters
    ----------
    profile_path:
        YAML profile path passed to :func:`lca_kernel.boot.run_kernel`.
    bootstrap_file_store:
        Optional FileStore injected into the ``file_store`` seam **before**
        plugin fibers spawn, mirroring the old ``profile_lifespan`` contract
        so test fixtures can pre-register an app-owned store.

    完整 K 链路地图见模块 docstring 的"启动全景"段。
    """
    from lca_kernel.boot import run_kernel  # ↓ K3:从 K6 进入 K3 主入口

    ctx = await run_kernel(
        profile_path, bootstrap_file_store=bootstrap_file_store
    )  # ↓ K3:跑 K1(解析)+K2(编译)+K3(cordis)+K5(观测),返回 booted ctx
    coordinator = create_shutdown_coordinator(ctx)  # ↑ K6:把 K3 返回的 ctx 绑给 ShutdownCoordinator
    install_signal_handlers(coordinator)  # ↓ K6:装 SIGTERM/SIGINT → coordinator.interrupt
    install_fail_loud(coordinator)  # ↓ K6:装 sys.excepthook + asyncio/threading 异常通道
    try:
        yield {"ctx": ctx}  # ↓ K0:把 ctx 交回 _lifespan,ASGI 进入"运行中"状态
    finally:
        await coordinator.shutdown(0)  # ↑ K6:lifespan 退出时 LIFO dispose + sys.exit(0)


__all__ = [
    "FAIL_LOUD_RELEASE_TIMEOUT_MS",
    "DefaultShutdownCoordinator",
    "ShutdownCoordinator",
    "create_shutdown_coordinator",
    "install_fail_loud",
    "install_signal_handlers",
    "run_kernel_lifespan",
]
