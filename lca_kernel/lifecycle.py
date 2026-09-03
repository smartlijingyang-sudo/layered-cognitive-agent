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
import logging
import signal
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# SSOT 异常归一化(ADR-2026-09-03 traceback-ssot-hook):三钩子兜底走这里
# 而非直接构造 dict payload。任何逃出 try/except 的异常必须在 traceback
# 丢失之前归一化成 ExceptionRecord,再 emit_exception_caught → spine。
# 公开名直接 import(供测试 monkeypatch + lint-imports whitelist)。
from lca.contracts.observability.exception_capture import exc_to_record
from lca.infrastructure.observability.spine.exception_emit import emit_exception_caught
from lca_kernel.errors import KernelError

log = logging.getLogger(__name__)

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
    """装 sys.excepthook + asyncio loop handler + threading.excepthook。

    ADR-2026-09-03 traceback-ssot-hook:三道异常通道的共享回调 **必须**
    先归一化异常到 SSOT(ExceptionRecord → emit_exception_caught),**然后**
    才触发 coordinator.interrupt(1) shutdown。原实现只触发 shutdown,
    异常信息丢失 → manifest.session_error 只有一行字符串,无 sidecar
    traceback。

    设计要点:
    1. **必须先 emit 再 shutdown**:emit 是同步 spine append,block 几十微秒;
       shutdown 走 async dispose,需要 event loop。这里先 emit 把异常写盘,
       再触发 interrupt,确保 traceback 进 spine(否则 shutdown 路径若异常
       递归,异常本体仍能进 spine)。
    2. **递归防护**:emit_exception_caught 自身可能抛(spine 未装 / OOM);
       fallback structlog,不让钩子 panic 触发再次 excepthook。
    3. **shutting_down 短路**:关闭期间再触发的异常 no-op,防重复 emit
       + 防止 coordinator.interrupt 在 shutdown 路径里再次触发自己。
    4. **FailLoudError 不再 raise**:旧实现 ``raise FailLoudError(...)`` 是
       给 supervisor 看的 exit code 标记,但该 raise 会被 sys.excepthook
       自己再次捕获 → 无限递归。删除 raise,改用 emit exception.caught
       event(outcome="failure") 作为 fail-loud 痕迹(下游 reader 已消费
       exception.caught 事件,FailLoudError 仅剩类型别名用于 type narrowing)。
    """
    if not isinstance(coordinator, DefaultShutdownCoordinator):
        raise TypeError(
            "install_fail_loud expects DefaultShutdownCoordinator",
        )

    # 进程级递归标志:同一线程内 emit 内部抛异常时,fallback 路径不要
    # 再次进入 emit。Python 没有线程级的"已捕获"状态,用模块级标志
    # + threading.Lock(主路径同步,线程路径并发)双重防护。
    _capture_lock = threading.Lock()
    _capturing = False

    def _capture(exc: BaseException, *, boundary: str) -> None:
        """归一化 + emit,失败 fallback structlog。绝不抛。"""
        nonlocal _capturing
        with _capture_lock:
            if _capturing:
                return
            _capturing = True
        try:
            try:
                record = exc_to_record(
                    exc,
                    boundary=boundary,
                    run_id="",
                    trace_id="",
                )
            except Exception:
                log.exception(
                    "lifecycle.fail_loud: exc_to_record failed boundary=%s",
                    boundary,
                )
                return
            try:
                emit_exception_caught(record)
            except Exception:
                log.exception(
                    "lifecycle.fail_loud: emit_exception_caught failed boundary=%s",
                    boundary,
                )
        finally:
            _capturing = False

    def _on_unhandled(
        exc_type: Any, exc_value: Any, _exc_tb: Any
    ) -> None:  # ↑ K6:三道异常通道的共享回调
        if coordinator.is_shutting_down:
            return  # ↑ K6:已在关闭中,不再重复触发
        # 第 1 步:归一化异常 → SSOT → emit(治本关键)
        # 仅处理真实异常实例,过滤掉 exc_value 是 None 的"空槽"场景
        # (asyncio handler 在 task.cancel() 时会传 None)。
        if isinstance(exc_value, BaseException):
            _capture(exc_value, boundary=f"lifecycle.fail_loud.{exc_type.__name__}")
        # 第 2 步:触发 shutdown(原行为保留)
        coordinator.interrupt(1)  # ↓ K6:fire-and-forget 触发 shutdown

    sys.excepthook = _on_unhandled  # ↓ K6:同步路径异常 → _on_unhandled
    # asyncio handler 装到 _currently_running loop 或 set_event_loop 的 loop。
    # get_running_loop 只在 loop 已在跑时返回,set_event_loop 是裸 install
    # 时的唯一抓手(K3 启动顺序中 loop 已 set_event_loop 但尚未 run_forever)。
    try:
        loop = asyncio.get_running_loop()  # ↑ K6:拿当前事件循环(可能尚未启动)
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
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
