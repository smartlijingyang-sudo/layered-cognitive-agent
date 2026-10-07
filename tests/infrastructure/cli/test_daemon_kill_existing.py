"""RA-006: the single-daemon invariant is owned by ``_kill_existing``.

restart() must kill the old process and confirm it is dead (pid_alive
flips true -> false) before start() spawns the new one. The previous
``time.sleep(0.5)`` timing hope is gone; the wait is bounded by timeout.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from lca.infrastructure.cli.config.config import DaemonConfig, KernelServeConfig
from lca.infrastructure.cli.service.service import ServiceState, ServiceStatus
from lca.infrastructure.cli.services.daemon import daemon as daemon_module
from lca.infrastructure.cli.services.daemon.daemon import (
    _CONNECT_PROC_PATTERN,
    DaemonService,
)


def _service(tmp_path: Path) -> tuple[DaemonService, MagicMock]:
    sudo = MagicMock()
    svc = DaemonService(
        config=DaemonConfig(),
        kernel_serve=KernelServeConfig(),
        state_dir=tmp_path,
        root=tmp_path,
        sudo=sudo,
    )
    return svc, sudo


def test_restart_waits_for_old_daemon_death_before_start(tmp_path: Path, monkeypatch) -> None:
    """pid_alive true -> false; start() is only called after death is confirmed."""
    svc, sudo = _service(tmp_path)
    sudo.read_text.return_value = "4242"

    events: list[tuple[str, object]] = []

    def fake_pid_alive(pid: int) -> bool:
        events.append(("pid_alive", pid))
        # True on the first poll (still dying), False on the second (dead).
        return len([e for e in events if e[0] == "pid_alive"]) == 1

    monkeypatch.setattr(daemon_module, "pid_alive", fake_pid_alive)

    started: list[str] = []

    def fake_start() -> ServiceState:
        started.append("start")
        return ServiceState(status=ServiceStatus.RUNNING)

    svc.start = fake_start  # type: ignore[method-assign]

    svc.restart()

    # Death confirmed (two polls: alive, then dead) BEFORE start was called.
    assert [e[0] for e in events] == ["pid_alive", "pid_alive"]
    assert events[0] == ("pid_alive", 4242)
    assert started == ["start"]
    # PR #40 behavior kept: the kill itself still goes through sudo pkill.
    sudo.run.assert_called_once_with(
        ["pkill", "-u", "sandbox-user", "-f", _CONNECT_PROC_PATTERN],
        timeout=10,
    )


def test_kill_existing_without_recorded_pid_skips_wait(tmp_path: Path, monkeypatch) -> None:
    """No pid file -> nothing to poll; pkill still sent, wait skipped."""
    svc, sudo = _service(tmp_path)
    sudo.read_text.return_value = None

    polled: list[int] = []
    monkeypatch.setattr(daemon_module, "pid_alive", lambda pid: polled.append(pid) or True)

    svc._kill_existing(_CONNECT_PROC_PATTERN, timeout=1.0)

    assert polled == []
    sudo.run.assert_called_once_with(
        ["pkill", "-u", "sandbox-user", "-f", _CONNECT_PROC_PATTERN],
        timeout=10,
    )


def test_connect_proc_pattern_is_single_source() -> None:
    """daemon.py owns the single public match string (RA-014).

    The private cross-seam import in user_cli.py is gone: host_runtime no
    longer reaches for the private name — the lifecycle seam (DaemonService)
    is the delegation contract.
    """
    import lca.infrastructure.host_runtime.providers.user_cli as user_cli_module

    assert daemon_module.CONNECT_PROC_PATTERN == "node.*index.js.*connect"
    assert _CONNECT_PROC_PATTERN is daemon_module.CONNECT_PROC_PATTERN
    assert not hasattr(user_cli_module, "_CONNECT_PROC_PATTERN")
