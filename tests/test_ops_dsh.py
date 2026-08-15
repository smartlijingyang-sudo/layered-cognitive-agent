"""lca-ops DSH service — SDK presence in the shared venv drives status and heal."""

from __future__ import annotations

from dataclasses import dataclass

from lca.layer0_infra.ops.config import DshConfig
from lca.layer0_infra.ops.service import ServiceStatus
from lca.layer0_infra.ops.services.dsh import DshObservation, DshService

INSTALL = "./deploy/dsh/install-dsh-sdk.sh"
VENV = "/opt/lca/venv"


@dataclass
class _FakeProbe:
    venv_exists: bool = True
    sdk_importable: bool = True
    install_script_exists: bool = True

    def observe(self) -> DshObservation:
        return DshObservation(
            venv_exists=self.venv_exists,
            sdk_importable=self.sdk_importable,
            install_script_exists=self.install_script_exists,
        )


def _svc(probe: _FakeProbe) -> DshService:
    return DshService(DshConfig(), probe=probe)


def test_status_ok_when_sdk_importable() -> None:
    state = _svc(_FakeProbe()).state()
    assert state.status == ServiceStatus.RUNNING
    assert state.next_action == ""
    assert VENV in state.detail


def test_status_asks_to_install_when_sdk_missing() -> None:
    state = _svc(_FakeProbe(sdk_importable=False)).state()
    assert state.status == ServiceStatus.STOPPED
    assert INSTALL in state.next_action
    assert "not importable" in state.why


def test_status_asks_to_provision_when_venv_missing() -> None:
    state = _svc(_FakeProbe(venv_exists=False, sdk_importable=False)).state()
    assert state.status == ServiceStatus.STOPPED
    assert "provision" in state.next_action


def test_heal_noop_when_already_running() -> None:
    probe = _FakeProbe()
    state = _svc(probe).heal()
    assert state.status == ServiceStatus.RUNNING


def test_stack_status_includes_dsh() -> None:
    from lca.layer0_infra.ops.steps import STATUS_SERVICES

    assert "dsh" in STATUS_SERVICES


def test_stack_stop_does_not_include_dsh() -> None:
    from lca.layer0_infra.ops.steps import STOP_SERVICES

    assert "dsh" not in STOP_SERVICES


def test_dsh_config_defaults() -> None:
    cfg = DshConfig()
    assert cfg.venv_dir == "/opt/lca/venv"
    assert cfg.install_cmd == INSTALL
    assert cfg.sdk_python.name == "python3"


def test_dsh_config_env_overlay(monkeypatch) -> None:
    from lca.layer0_infra.ops.config import OpsConfig

    monkeypatch.setenv("DSH_VENV_DIR", "/custom/venv")
    cfg = OpsConfig.load(None)
    assert cfg.dsh.venv_dir == "/custom/venv"
