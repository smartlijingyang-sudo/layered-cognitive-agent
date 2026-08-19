"""lca-ops lobehub status must treat HTTP reachability as ground truth."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lca.layer0_infra.ops.config import GatewayConfig, LobeHubConfig
from lca.layer0_infra.ops.service import ServiceStatus
from lca.layer0_infra.ops.services.lobehub import LobeHubService
from lca.layer0_infra.ops.state import StateStore


@pytest.fixture
def lobehub_svc(tmp_path: Path) -> LobeHubService:
    root = tmp_path / "repo"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text('{"version": "2.2.13"}')
    (ui_dir / ".lca-patched").write_text("ok")
    deploy_dir = root / "deploy" / "lobehub" / "patches"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "sample.py").write_text("# patch\n")

    state_dir = tmp_path / "state"
    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        GatewayConfig(port=8765),
        state_dir,
        root,
    )
    StateStore(state_dir).save_snapshot("patches", [root / "deploy" / "lobehub"], "*")
    return svc


def test_status_running_when_dev_up_but_stored_pid_stale(lobehub_svc: LobeHubService) -> None:
    """next-server may outlive the bun parent recorded in the pid file."""
    lobehub_svc._state.write_pid("lobehub", 999_999)

    with (
        patch("lca.layer0_infra.ops.services.lobehub.http_ready", return_value=True),
        patch("lca.layer0_infra.ops.services.lobehub.pid_on_port", return_value=42_001),
        patch(
            "lca.layer0_infra.ops.services.lobehub.pid_alive", side_effect=lambda pid: pid == 42_001
        ),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.RUNNING
    assert state.is_running
    assert not state.next_action
    assert lobehub_svc._state.read_pid("lobehub") == 42_001


def test_status_stopped_when_dev_down_and_pid_stale(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 999_999)

    with (
        patch("lca.layer0_infra.ops.services.lobehub.http_ready", return_value=False),
        patch("lca.layer0_infra.ops.services.lobehub.pid_on_port", return_value=None),
        patch("lca.layer0_infra.ops.services.lobehub.pid_alive", return_value=False),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.STOPPED
    assert state.next_action == "./scripts/lca-ops lobehub start"


def _port_pid(next_pid: int | None, spa_pid: int | None = None):
    def _lookup(port: int) -> int | None:
        if port == 3010:
            return next_pid
        if port == 9876:
            return spa_pid
        return None

    return _lookup


def test_start_spawns_next_and_spa_not_coupled_dev(lobehub_svc: LobeHubService) -> None:
    spawned: list[list[str]] = []

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def _popen(cmd: object, **_kwargs: object) -> _Proc:
        spawned.append(list(cmd))  # type: ignore[arg-type]
        return _Proc(100 + len(spawned))

    with (
        patch.object(lobehub_svc, "ensure_ready", return_value=False),
        patch("lca.layer0_infra.ops.services.lobehub.subprocess.Popen", side_effect=_popen),
        patch("lca.layer0_infra.ops.services.lobehub.http_ready", return_value=True),
        patch("lca.layer0_infra.ops.services.lobehub.time.sleep"),
        patch("lca.layer0_infra.ops.services.lobehub.pid_on_port", side_effect=_port_pid(None, None)),
    ):
        state = lobehub_svc.start()

    assert state.status == ServiceStatus.RUNNING
    scripts = [cmd for cmd in spawned]
    assert ["bun", "run", "dev"] not in scripts
    assert ["bun", "run", "dev:next"] in scripts
    assert ["bun", "run", "dev:spa"] in scripts
    assert lobehub_svc._state.read_pid("lobehub") == 101
    assert lobehub_svc._state.read_pid("lobehub-spa") == 102


def test_next_up_spa_down_is_degraded_not_stopped(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 42_001)

    with (
        patch("lca.layer0_infra.ops.services.lobehub.http_ready", return_value=True),
        patch("lca.layer0_infra.ops.services.lobehub.pid_on_port", side_effect=_port_pid(42_001, None)),
        patch("lca.layer0_infra.ops.services.lobehub.pid_alive", side_effect=lambda pid: pid == 42_001),
    ):
        state = lobehub_svc.state()

    assert state.status == ServiceStatus.DEGRADED
    assert state.pid == 42_001
    assert any(c.name == "spa" and not c.ok for c in state.checks)
    assert state.next_action == "./scripts/lca-ops lobehub heal"


def test_heal_spa_only_does_not_respawn_next(lobehub_svc: LobeHubService) -> None:
    lobehub_svc._state.write_pid("lobehub", 42_001)
    spawned: list[list[str]] = []

    class _Proc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def _popen(cmd: object, **_kwargs: object) -> _Proc:
        spawned.append(list(cmd))  # type: ignore[arg-type]
        return _Proc(77)

    with (
        patch.object(lobehub_svc, "ensure_ready", return_value=False),
        patch.object(lobehub_svc, "stop") as stop,
        patch("lca.layer0_infra.ops.services.lobehub.subprocess.Popen", side_effect=_popen),
        patch("lca.layer0_infra.ops.services.lobehub.http_ready", return_value=True),
        patch(
            "lca.layer0_infra.ops.services.lobehub.pid_on_port",
            side_effect=_port_pid(42_001, None),
        ),
        patch("lca.layer0_infra.ops.services.lobehub.pid_alive", side_effect=lambda pid: pid in {42_001, 77}),
    ):
        state = lobehub_svc.heal()

    stop.assert_not_called()
    assert spawned == [["bun", "run", "dev:spa"]]
    assert lobehub_svc._state.read_pid("lobehub") == 42_001
    assert lobehub_svc._state.read_pid("lobehub-spa") == 77
    assert state.status == ServiceStatus.DEGRADED or state.pid == 42_001
