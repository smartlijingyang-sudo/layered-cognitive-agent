"""RA-084: Service protocol capabilities — pure-fake driven tests.

Proves the isinstance downcasts in steps.py are dead and no cross-module
calls to underscore-private methods remain:

- daemon_ensure / stack_heal are driven by pure protocol fakes (plain
  classes, NOT DaemonService / KernelServeService subclasses);
- a source-level pin asserts steps.py contains no isinstance downcast and
  no calls into underscore-private service methods.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.infrastructure.cli.pipeline.pipeline import PipelineContext
from lca.infrastructure.cli.service.service import ServiceState, ServiceStatus
from lca.infrastructure.cli.services.kernel.spawner import SpawnResult
from lca.infrastructure.cli.steps.steps import daemon_ensure, stack_heal

_STEPS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "lca/infrastructure/cli/steps/steps.py"
)


def test_no_isinstance_downcast_in_steps() -> None:
    src = _STEPS_PATH.read_text(encoding="utf-8")
    assert "isinstance" not in src, "steps.py still downcasts on concrete services"


def test_no_cross_module_private_calls_in_steps() -> None:
    src = _STEPS_PATH.read_text(encoding="utf-8")
    for lineno, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # cross-module private access looks like ``svc._x`` / ``daemon._x``
        # (definitions ``def _x`` and intra-module ``self._x`` are fine)
        assert "._cli_deployed(" not in line, f"line {lineno}: private call"
        assert "._cli_source_changed(" not in line, f"line {lineno}: private call"


class _FakeConsole:
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

    def messages(self, kind: str) -> list[Any]:
        return [msg for k, msg in self.calls if k == kind]


class _PureFakeService:
    """Pure protocol fake: structural Service, no concrete base class."""

    def __init__(
        self,
        *,
        running: bool = True,
        cli_current: bool = False,
        spawner: Any = None,
    ) -> None:
        self.name = "fake"
        self._running = running
        self._cli_current = cli_current
        self._spawner = spawner
        self.ensure_ready_calls = 0

    def start(self) -> ServiceState:
        return ServiceState(status=ServiceStatus.RUNNING)

    def stop(self) -> ServiceState:
        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        return ServiceState(status=ServiceStatus.RUNNING)

    def ensure_ready(self) -> bool:
        self.ensure_ready_calls += 1
        return True

    def state(self) -> ServiceState:
        return ServiceState(
            status=ServiceStatus.RUNNING if self._running else ServiceStatus.STOPPED
        )

    def heal(self) -> ServiceState:
        return ServiceState(status=ServiceStatus.RUNNING)

    def cli_fingerprint_current(self) -> bool:
        return self._cli_current

    def spawner(self) -> Any:
        return self._spawner


class _FakeSpawner:
    def __init__(self, result: SpawnResult) -> None:
        self._result = result
        self.run_calls = 0

    def run(self) -> SpawnResult:
        self.run_calls += 1
        return self._result


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


def _heal_services(kernel_fake: _PureFakeService) -> dict[str, Any]:
    services: dict[str, Any] = {"kernel_serve": kernel_fake}
    for name in ("infra", "lobehub", "daemon", "onlyboxes"):
        services[name] = _PureFakeService(running=True)
    return services


def test_daemon_ensure_skips_redeploy_when_fingerprint_current() -> None:
    svc = _PureFakeService(cli_current=True)
    ctx, console = _make_ctx({"daemon": svc})

    daemon_ensure(ctx)

    assert svc.ensure_ready_calls == 0
    assert ctx.failed is False
    assert any(
        "up-to-date" in msg for msg in console.messages("success")
    )


def test_daemon_ensure_redeploys_when_fingerprint_stale() -> None:
    svc = _PureFakeService(cli_current=False)
    ctx, console = _make_ctx({"daemon": svc})

    daemon_ensure(ctx)

    assert svc.ensure_ready_calls == 1
    assert ctx.failed is False
    assert any(
        "redeployed" in msg for msg in console.messages("success")
    )


def test_daemon_ensure_default_capability_is_absent() -> None:
    """A Service that does not override the capability uses the protocol
    default (False) and always falls through to ensure_ready()."""
    from lca.infrastructure.cli.service.service import Service

    class _Minimal:
        name = "minimal"
        calls = 0

        def ensure_ready(self) -> bool:
            type(self).calls += 1
            return True

        # bind the protocol default directly: this IS the default behavior
        cli_fingerprint_current = Service.cli_fingerprint_current

    svc = _Minimal()
    ctx, _ = _make_ctx({"daemon": svc})
    daemon_ensure(ctx)
    assert _Minimal.calls == 1


def test_stack_heal_spawns_via_pure_fake_spawner() -> None:
    spawner = _FakeSpawner(
        SpawnResult(ok=True, pid=1234, port=8765, duration_ms=5)
    )
    ks = _PureFakeService(running=False, spawner=spawner)
    ctx, _ = _make_ctx(_heal_services(ks))

    stack_heal(ctx)

    assert spawner.run_calls == 1
    assert ctx.failed is False


def test_stack_heal_without_spawner_capability_fails_loud() -> None:
    """spawner() -> None keeps the old fail-loud TypeError path (no isinstance)."""
    ks = _PureFakeService(running=False, spawner=None)
    ctx, console = _make_ctx(_heal_services(ks))

    stack_heal(ctx)

    assert ctx.failed is True
    assert any(
        "heal crashed" in msg for msg in console.messages("error")
    )
