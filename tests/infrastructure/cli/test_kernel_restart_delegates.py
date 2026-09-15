"""`lca-ops kernel-restart` delegates to the supervisor and builds no context.

The command is a thin wrapper: it reads a program config, asks the supervisor to
restart, waits for readiness and renders the same report
`kernel-supervisor restart` produces. It used to start by constructing a
`PipelineContext` it never passed on — which, because `make_context` loads
`OpsConfig`, builds the service registry and opens `StateStore(config.state_dir)`
(creating that directory as a side effect), meant every convenience restart
touched ops state it does not use.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    import pytest

from lca.infrastructure.cli.commands.runs import workflow


def _command(name: str) -> Any:
    app = typer.Typer()
    workflow.register(app)
    for info in app.registered_commands:
        if info.name == name:
            assert info.callback is not None
            return info.callback
    raise AssertionError(f"command {name!r} is not registered by workflow.register()")


class _StubSupervisor:
    def __init__(self) -> None:
        self.restarts = 0
        self.wait_timeouts: list[float] = []

    def restart(self) -> None:
        self.restarts += 1

    def wait_ready(self, timeout: float | None = None) -> bool:
        self.wait_timeouts.append(timeout if timeout is not None else -1.0)
        return True

    def status(self) -> dict[str, object]:
        return {"state": "running"}


def test_kernel_restart_does_not_construct_a_pipeline_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("kernel-restart must not build a PipelineContext; nothing consumes it")

    monkeypatch.setattr(workflow, "make_context", _forbidden)

    services = importlib.import_module("lca.infrastructure.cli.services.kernel.supervisor")
    rendered: list[object] = []
    supervisor = _StubSupervisor()
    cfg = SimpleNamespace(readiness_timeout=3.0)
    monkeypatch.setattr(services, "default_program_config", lambda: cfg)
    monkeypatch.setattr(services, "get_supervisor", lambda _cfg: supervisor)
    monkeypatch.setattr(
        services,
        "build_restart_result",
        lambda _cfg, status, ready: {"verdict": "ok", "status": status, "ready": ready},
    )
    commands = importlib.import_module("lca.infrastructure.cli.commands.kernel.supervisor")
    monkeypatch.setattr(commands, "_render", lambda report, json_mode: rendered.append(report))

    _command("kernel-restart")(json_mode=True, quiet=False, config=None)

    assert supervisor.restarts == 1
    assert supervisor.wait_timeouts == [3.0]
    assert rendered == [{"verdict": "ok", "status": {"state": "running"}, "ready": True}]
