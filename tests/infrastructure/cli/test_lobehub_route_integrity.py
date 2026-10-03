"""Route-collapse detection and heal behavior for LobeHubService.

Regression for the 2026-10-03 frontend outage: after a failed heal restart
hit ``EADDRINUSE``, the dev route table collapsed to only ``/_not-found`` and
every URL bounced ``/`` <-> ``/signin``. ``http_ready`` treats 3xx as healthy,
so ``state()`` reported RUNNING and the watchdog never re-healed. These tests
pin the new ``/signin`` route-integrity probe and the forced-restart path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from lca.infrastructure.cli.service.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
)


@pytest.fixture
def lobehub_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build a LobeHubService isolated from the host environment."""
    from lca.infrastructure.cli.config.config import OpsConfig
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    cfg_path = tmp_path / "lca-ops.yaml"
    cfg_path.write_text(
        "kernel_serve:\n  host: 10.36.6.252\n  port: 8765\n  health_path: /health\n"
        "  profile: profiles/web-standard.yaml\n"
        "lobehub:\n  host: 10.36.6.252\n  release: v2.2.13\n  dir: lobehub-ui\n"
        "  dev_port: 3010\n  spa_port: 9876\n  env_template: deploy/lobehub/.env.lca\n"
    )
    cfg = OpsConfig.load(cfg_path)
    monkeypatch.setattr("os.environ", {}, raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return LobeHubService(
        config=cfg.lobehub,
        gateway=cfg.kernel_serve,
        state_dir=state_dir,
        root=tmp_path,
    )


def _stub_network(monkeypatch: pytest.MonkeyPatch, signin_code: int) -> None:
    """Stub process/port probes so state() runs without a live dev server."""
    import lca.infrastructure.cli.services.lobehub.lobehub as lobehub

    monkeypatch.setattr(lobehub, "http_ready", lambda url, timeout=2.0: True)
    monkeypatch.setattr(lobehub, "pid_on_port", lambda port: 4242)
    monkeypatch.setattr(lobehub, "pid_alive", lambda pid: True)
    monkeypatch.setattr(lobehub, "http_code", lambda url, timeout=2.0: signin_code)


def test_state_reports_route_collapse_when_signin_redirects(
    lobehub_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/signin answering 307 must mark the service degraded for a restart."""
    _stub_network(monkeypatch, signin_code=307)

    state = lobehub_service.state()

    assert state.status == ServiceStatus.DEGRADED
    assert state.next_action == "./scripts/lca-ops lobehub restart"
    routes_check = next(c for c in state.checks if c.name == "routes")
    assert routes_check.ok is False
    assert "307" in routes_check.detail


def test_state_running_when_signin_answers_200(
    lobehub_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/signin returning 200 keeps the service RUNNING (healthy path)."""
    _stub_network(monkeypatch, signin_code=200)

    state = lobehub_service.state()

    assert state.status == ServiceStatus.RUNNING
    routes_check = next(c for c in state.checks if c.name == "routes")
    assert routes_check.ok is True


def test_heal_forces_stop_on_route_collapse(
    lobehub_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route collapse must stop the still-responding listener before start.

    ``current.is_running`` is False for DEGRADED, so heal would otherwise skip
    stop() and start() would reuse the broken listener via http_ready.
    """
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    svc: LobeHubService = lobehub_service
    current = ServiceState(
        status=ServiceStatus.DEGRADED,
        detail="routes collapsed (/signin redirects)",
        next_action="./scripts/lca-ops lobehub restart",
        checks=(
            HealthCheck("dev", True, ":3010"),
            HealthCheck("spa", True, ":9876"),
            HealthCheck("routes", False, "/signin -> 307"),
            HealthCheck("patches", True, "44/44 verified"),
        ),
    )
    svc.state = Mock(return_value=current)  # type: ignore[method-assign]
    svc.stop = Mock()  # type: ignore[method-assign]
    svc.start = Mock(return_value=ServiceState(status=ServiceStatus.RUNNING))  # type: ignore[method-assign]
    svc.ensure_ready = Mock(return_value=True)  # type: ignore[method-assign]

    result = svc.heal()

    svc.stop.assert_called_once()
    svc.ensure_ready.assert_called_once()
    svc.start.assert_called_once()
    assert result.status == ServiceStatus.RUNNING
