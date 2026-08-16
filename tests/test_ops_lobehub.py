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
