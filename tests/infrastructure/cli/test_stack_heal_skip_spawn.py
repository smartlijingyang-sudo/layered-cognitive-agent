"""stack.heal kernel_serve 分支行为测试（ADR-0213 PR-3）。

回归锁（2bb3ceefc / e51902b07 RET505 误判）：``stack_heal`` 在
kernel 已健康时必须跳过 ``spawner().run()`` —— e51902b07 把 ``else:``
拿掉后，健康路径 fall-through 到了 spawn 分支，同端口重复拉起 kernel
且 heal 误报失败。本文件钉住三条行为：

1. 已健康 → 不调 ``spawner()``（锋利断言：调了就抛）。
2. 不健康 → 调一次 ``spawner().run()``。
3. spawn 失败 → ``ctx.failed`` 置位、leftover 落盘。

全部只碰 tests 树，用测试替身隔离 HTTP/进程，不起真 kernel。
"""

from __future__ import annotations

from typing import Any

from lca.infrastructure.cli.pipeline.pipeline import PipelineContext
from lca.infrastructure.cli.service.service import ServiceState, ServiceStatus
from lca.infrastructure.cli.services.kernel.serve import KernelServeService
from lca.infrastructure.cli.services.kernel.spawner import SpawnResult
from lca.infrastructure.cli.steps.steps import stack_heal


class _FakeConsole:
    """记录调用的 console 替身（只实现 stack_heal 用到的方法）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def info(self, msg: str) -> None:
        self.calls.append(("info", msg))

    def error(self, msg: str) -> None:
        self.calls.append(("error", msg))

    def warning(self, msg: str) -> None:
        self.calls.append(("warning", msg))

    def success(self, msg: str) -> None:
        self.calls.append(("success", msg))

    def service_state(self, name: str, state: Any) -> None:
        self.calls.append(("service_state", name))

    def next_steps(self, actions: list[str]) -> None:
        self.calls.append(("next_steps", actions))

    def messages(self, kind: str) -> list[Any]:
        return [msg for k, msg in self.calls if k == kind]


class _FakeSpawner:
    def __init__(self, result: SpawnResult) -> None:
        self._result = result
        self.run_calls = 0

    def run(self) -> SpawnResult:
        self.run_calls += 1
        return self._result


class _FakeExternalService:
    """STATUS_SERVICES 里的外部服务：heal() 返回健康。"""

    def heal(self) -> ServiceState:
        return ServiceState(status=ServiceStatus.RUNNING)


def _kernel_service(*, running: bool, spawner: Any) -> KernelServeService:
    ks = KernelServeService.__new__(KernelServeService)
    state = ServiceState(
        status=ServiceStatus.RUNNING if running else ServiceStatus.STOPPED
    )
    ks.state = lambda: state  # type: ignore[method-assign]
    ks.spawner = spawner  # type: ignore[method-assign]
    return ks


def _make_ctx(services: dict[str, Any]) -> tuple[PipelineContext, _FakeConsole]:
    console = _FakeConsole()
    registry = type(
        "_FakeRegistry", (), {"get": lambda self, name: services[name]}
    )()
    ctx = PipelineContext(
        config=object(),  # type: ignore[arg-type]
        registry=registry,  # type: ignore[arg-type]
        state=object(),  # type: ignore[arg-type]
        console=console,  # type: ignore[arg-type]
    )
    return ctx, console


def _base_services(ks: KernelServeService) -> dict[str, Any]:
    services: dict[str, Any] = {"kernel_serve": ks}
    for name in ("infra", "lobehub", "daemon", "onlyboxes"):
        services[name] = _FakeExternalService()
    return services


def test_stack_heal_healthy_kernel_skips_spawn() -> None:
    """回归锁(2bb3ceefc):kernel 已健康 → ``spawner()`` 一次都不能被调。

    e51902b07 误判后健康路径 fall-through 到 spawn 分支，同端口重复
    spawn；锋利断言：调 ``spawner()`` 即抛，bug 复现即红。
    """

    def _explode() -> Any:
        raise AssertionError("spawner() must not be called when kernel is healthy")

    ks = _kernel_service(running=True, spawner=_explode)
    ctx, console = _make_ctx(_base_services(ks))

    stack_heal(ctx)

    assert ctx.failed is False
    assert "spawn failed" not in "".join(console.messages("error"))
    assert "kernel_serve" not in "".join(console.messages("warning"))


def test_stack_heal_unhealthy_kernel_spawns_once() -> None:
    """不健康 → ``spawner().run()`` 恰好调一次；成功后不置 failed。"""
    spawner = _FakeSpawner(SpawnResult(ok=True, pid=1234, port=8765, duration_ms=5))
    ks = _kernel_service(running=False, spawner=lambda: spawner)
    ctx, _ = _make_ctx(_base_services(ks))

    stack_heal(ctx)

    assert spawner.run_calls == 1
    assert ctx.failed is False


def test_stack_heal_spawn_failure_marks_failed() -> None:
    """spawn 失败 → ``ctx.failed`` 置位，leftover 含 spawn 失败说明。"""
    spawner = _FakeSpawner(
        SpawnResult(ok=False, port=8765, exit_code=1, duration_ms=5)
    )
    ks = _kernel_service(running=False, spawner=lambda: spawner)
    ctx, console = _make_ctx(_base_services(ks))

    stack_heal(ctx)

    assert spawner.run_calls == 1
    assert ctx.failed is True
    assert any("spawn failed" in msg for msg in console.messages("error"))
    assert "heal could not finish:" in console.messages("warning")
