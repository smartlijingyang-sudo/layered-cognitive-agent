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
import typing
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

    def status(self) -> Any:
        # Return the real ProgramStatus shape so the post-restart SOP
        # report can read ``status.state.value`` / ``status.last_event``
        # without re-discovering the contract through a dict.
        from lca.infrastructure.cli.services.kernel.supervisor import (
            ProgramState,
            ProgramStatus,
        )

        return ProgramStatus(
            name="lca_kernel_dev",
            state=ProgramState.RUNNING,
            pid=None,
            uptime_s=0.0,
            restart_count=0,
            last_exit_code=None,
            last_event="readiness probe passed",
            spawned_at=None,
        )


def test_kernel_restart_does_not_construct_a_pipeline_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("kernel-restart must not build a PipelineContext; nothing consumes it")

    monkeypatch.setattr(workflow, "make_context", _forbidden)

    services = importlib.import_module("lca.infrastructure.cli.services.kernel.supervisor")
    rendered: list[object] = []
    supervisor = _StubSupervisor()
    cfg = SimpleNamespace(
        readiness_timeout=3.0,
        host=lambda: "127.0.0.1",
        port=lambda: 8765,
    )
    monkeypatch.setattr(services, "default_program_config", lambda: cfg)
    monkeypatch.setattr(services, "get_supervisor", lambda _cfg: supervisor)
    monkeypatch.setattr(
        services,
        "build_restart_result",
        lambda _cfg, status, ready: {"verdict": "ok", "status": status, "ready": ready},
    )
    commands = importlib.import_module("lca.infrastructure.cli.commands.kernel.supervisor")
    monkeypatch.setattr(commands, "_render", lambda report, json_mode: rendered.append(report))

    # Stub the post-restart SOP report so the test does not depend on a
    # live kernel hitting /health or the kernel stderr log file.
    restart_report_mod = importlib.import_module(
        "lca.infrastructure.cli.services.kernel.restart_report"
    )

    class _StubReport:
        ok: typing.ClassVar[bool] = True
        profile: typing.ClassVar[str] = "profiles/web-standard.yaml"
        phases: typing.ClassVar[list[object]] = []
        findings: typing.ClassVar[list[object]] = []
        duration_ms: typing.ClassVar[int] = 0
        supervisor_state: typing.ClassVar[str] = "running"
        supervisor_last_event: typing.ClassVar[str] = "readiness probe passed"
        next_command: typing.ClassVar[object] = None

        def to_dict(self) -> dict[str, object]:
            return {
                "ok": True,
                "profile": self.profile,
                "phases": [],
                "findings": [],
                "duration_ms": 0,
                "supervisor_state": self.supervisor_state,
                "supervisor_last_event": self.supervisor_last_event,
                "next_command": None,
            }

    captured_kwargs: dict[str, object] = {}

    def _stub_run_restart_report(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return _StubReport()

    # ``workflow.kernel_restart`` imports ``restart_report`` at the top of
    # its function body, so we patch the names on the module object —
    # not the module attribute on ``workflow``.
    monkeypatch.setattr(restart_report_mod, "run_restart_report", _stub_run_restart_report)
    monkeypatch.setattr(restart_report_mod, "should_quiet", lambda: True)
    monkeypatch.setattr(restart_report_mod, "render_text", lambda _r: "")

    _command("kernel-restart")(json_mode=True, quiet=False, config=None)

    assert supervisor.restarts == 1
    assert supervisor.wait_timeouts == [3.0]
    # The SOP report must have been driven by the supervisor stub's status,
    # not by anything the test injected. The host/port must also have come
    # from the ProgramConfig-like namespace. In json_mode the command does
    # not invoke _render (it prints JSON directly), so we assert against
    # the captured kwargs instead.
    assert captured_kwargs["supervisor_state"] == "running"
    assert captured_kwargs["host"] == "127.0.0.1"
    assert captured_kwargs["port"] == 8765
