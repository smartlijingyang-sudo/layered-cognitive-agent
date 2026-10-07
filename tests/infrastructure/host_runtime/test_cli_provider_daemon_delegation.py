"""RA-014: CLIProvider delegates the connect-daemon lifecycle to DaemonService.

The daemon-lifecycle seam is injected, so these tests nail the delegation
contract with a fake service — no subprocess/sudo runs. The lazy factory
(``_daemon_service_for``) is covered for its config mapping under a tmp cwd
so no repo-local ``.lca-ops`` dir is created.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.infrastructure.cli.service.service import ServiceState, ServiceStatus
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


def test_heal_restarts_daemon_through_seam() -> None:
    daemon = MagicMock()
    daemon.start.return_value = _running_state()
    check = CheckResult(name="daemon", status=ItemStatus.MISSING)
    assert _provider(daemon).heal(check) is True
    daemon.stop.assert_called_once_with()
    daemon.start.assert_called_once_with()


def test_heal_ignores_non_daemon_checks() -> None:
    daemon = MagicMock()
    check = CheckResult(name="deployed", status=ItemStatus.MISSING)
    assert _provider(daemon).heal(check) is False
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


def test_kernel_serve_status_converges_on_http_ready(monkeypatch) -> None:
    import lca.infrastructure.host_runtime.providers.user_cli as user_cli_module

    seen: list[tuple[str, float]] = []
    def fake_http_ready(url: str, timeout: float = 2.0) -> bool:
        seen.append((url, timeout))
        return True

    monkeypatch.setattr(user_cli_module, "http_ready", fake_http_ready)
    from lca.infrastructure.host_runtime.providers import StatusReport

    report = StatusReport("cli:sandbox-user")
    _provider(MagicMock())._report_kernel_serve_status(report)
    checks = {c.name: c for c in report.checks}
    assert seen == [("http://10.36.6.252:8765/health", 5.0)]
    assert checks["kernel_serve"].status == ItemStatus.OK


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
