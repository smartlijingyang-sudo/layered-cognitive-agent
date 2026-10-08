"""RA-014/RA-028: CLIProvider delegates the connect-daemon lifecycle *and* its
status/heal observation to DaemonService.

The daemon-lifecycle seam is injected, so these tests nail the delegation
contract with a fake service — no subprocess/sudo runs, no pid file on disk.
The lazy factory (``_daemon_service_for``) is covered for its config mapping
under a tmp cwd so no repo-local ``.lca-ops`` dir is created.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.infrastructure.cli.service.service import HealthCheck, ServiceState, ServiceStatus
from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.infrastructure.host_runtime.providers import CheckResult, ItemStatus
from lca.infrastructure.host_runtime.providers.user_cli import CLIProvider, _daemon_service_for


def _running_state() -> ServiceState:
    return ServiceState(status=ServiceStatus.RUNNING, pid=1234, detail="connected")


def _stopped_state() -> ServiceState:
    return ServiceState(status=ServiceStatus.STOPPED, detail="stopped")


def _provider(daemon: MagicMock | None = None) -> CLIProvider:
    return CLIProvider(
        HostRuntimeConfig(),
        user=UserConfig(name="sandbox-user"),
        daemon=daemon,
    )


def _state_with(*checks: HealthCheck) -> ServiceState:
    return ServiceState(status=ServiceStatus.RUNNING, checks=checks)


def test_start_daemon_delegates_to_seam() -> None:
    daemon = MagicMock()
    daemon.start.return_value = _running_state()
    assert _provider(daemon).start_daemon() is True
    daemon.start.assert_called_once_with()


def test_start_daemon_maps_stopped_state_to_false() -> None:
    daemon = MagicMock()
    daemon.start.return_value = _stopped_state()
    assert _provider(daemon).start_daemon() is False


def test_stop_daemon_delegates_to_seam() -> None:
    daemon = MagicMock()
    daemon.stop.return_value = _stopped_state()
    assert _provider(daemon).stop_daemon() is True
    daemon.stop.assert_called_once_with()


def test_heal_restarts_through_seam_restart() -> None:
    """RA-028: heal() goes through DaemonService.restart(), not hand-rolled
    stop_daemon()+start_daemon() — the RA-006 single-instance invariant is
    owned by the seam."""
    daemon = MagicMock()
    daemon.restart.return_value = _running_state()
    check = CheckResult(name="daemon", status=ItemStatus.MISSING)
    assert _provider(daemon).heal(check) is True
    daemon.restart.assert_called_once_with()
    daemon.stop.assert_not_called()
    daemon.start.assert_not_called()


def test_heal_maps_stopped_restart_to_false() -> None:
    daemon = MagicMock()
    daemon.restart.return_value = _stopped_state()
    check = CheckResult(name="daemon", status=ItemStatus.MISSING)
    assert _provider(daemon).heal(check) is False


def test_heal_ignores_non_daemon_checks() -> None:
    daemon = MagicMock()
    check = CheckResult(name="deployed", status=ItemStatus.MISSING)
    assert _provider(daemon).heal(check) is False
    daemon.restart.assert_not_called()
    daemon.stop.assert_not_called()
    daemon.start.assert_not_called()


def test_start_daemon_without_user_returns_false() -> None:
    daemon = MagicMock()
    provider = CLIProvider(HostRuntimeConfig(), daemon=daemon)
    assert provider.start_daemon() is False
    daemon.start.assert_not_called()


def test_stop_daemon_without_user_returns_true() -> None:
    daemon = MagicMock()
    provider = CLIProvider(HostRuntimeConfig(), daemon=daemon)
    assert provider.stop_daemon() is True
    daemon.stop.assert_not_called()


def test_private_pid_alive_replica_is_gone() -> None:
    assert not hasattr(CLIProvider, "_pid_alive")


def test_status_projects_daemon_and_gateway_from_seam_state() -> None:
    """RA-028: daemon liveness + gateway reachability come from the injected
    seam's state(), not from pid-file reads or direct http probes.

    No connect.pid exists on disk in this test — the fake seam is the only
    source of daemon truth (pins the acceptance criterion directly)."""
    daemon = MagicMock()
    daemon.state.return_value = _state_with(
        HealthCheck("daemon", True, "pid=1234"),
        HealthCheck("gateway", True, "reachable"),
    )
    provider = _provider(daemon)
    report = provider.status()
    checks = {c.name: c for c in report.checks}
    daemon.state.assert_called_once_with()
    assert checks["daemon"].status == ItemStatus.OK
    assert checks["daemon"].detail == "pid=1234"
    assert checks["kernel_serve"].status == ItemStatus.OK
    assert checks["kernel_serve"].detail == "reachable"
    # the CLI-deployed check stays in the provider: it mirrors the
    # provider's own _cli_js artifact check, independent of the seam
    assert checks["deployed"].detail == str(provider.config.paths.cli_dir)
    assert (checks["deployed"].status == ItemStatus.OK) == provider._cli_js.is_file()


def test_status_reports_daemon_down_and_gateway_unreachable() -> None:
    daemon = MagicMock()
    daemon.state.return_value = _state_with(
        HealthCheck("daemon", False, "not running"),
        HealthCheck("gateway", False, "unreachable"),
    )
    report = _provider(daemon).status()
    checks = {c.name: c for c in report.checks}
    assert checks["daemon"].status == ItemStatus.MISSING
    assert checks["daemon"].detail == "not running"
    # gateway unreachability stays a warning, not a failure (severity contract)
    assert checks["kernel_serve"].status == ItemStatus.WARN
    assert checks["kernel_serve"].detail == "unreachable"


def test_status_fails_loud_when_seam_omits_daemon_check() -> None:
    """An owner state without the daemon check is a hard fail, not a silent
    skip — it would mean the seam drifted under us."""
    daemon = MagicMock()
    daemon.state.return_value = _state_with(
        HealthCheck("gateway", True, "reachable"),
    )
    report = _provider(daemon).status()
    checks = {c.name: c for c in report.checks}
    assert checks["daemon"].status == ItemStatus.MISSING
    assert "daemon" in checks["daemon"].detail
    assert checks["kernel_serve"].status == ItemStatus.OK


def test_status_without_user_skips_daemon_observation() -> None:
    daemon = MagicMock()
    provider = CLIProvider(HostRuntimeConfig(), daemon=daemon)
    report = provider.status()
    checks = {c.name: c for c in report.checks}
    assert "daemon" not in checks
    assert "kernel_serve" not in checks
    daemon.state.assert_not_called()


def test_daemon_service_for_maps_host_runtime_config(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config = HostRuntimeConfig()
    service = _daemon_service_for(config, UserConfig(name="sandbox-user"))
    assert service._config.user == "sandbox-user"
    assert service._config.cli_dir == config.paths.cli_dir
    assert service._config.token == config.kernel_serve.token
    assert service._config.kernel_serve_ws_url == config.kernel_serve.url
    # health_url is re-split into host/port/path; the seam must probe the
    # same endpoint the host runtime reports on.
    assert service._kernel_serve_health_url == config.kernel_serve.health_url
