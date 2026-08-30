"""Host runtime profile is the SSOT for user and workspace."""

from __future__ import annotations

from lca.infrastructure.sandbox.host_settings import HostRuntimeSettings


def test_root_derived_from_user() -> None:
    cfg = HostRuntimeSettings(user="agent-box", root="")
    assert cfg.operator() == "agent-box"
    assert cfg.workspace().as_posix() == "/home/agent-box"


def test_explicit_root_wins() -> None:
    cfg = HostRuntimeSettings(user="agent-box", root="/var/lib/lca/ws")
    assert cfg.workspace().as_posix() == "/var/lib/lca/ws"
    assert cfg.outputs_dir().as_posix() == "/var/lib/lca/ws/outputs"


def test_shell_export_has_no_hardcoded_home() -> None:
    cfg = HostRuntimeSettings(user="box", root="")
    text = cfg.as_shell()
    assert "LCA_HOST_USER='box'" in text
    assert "LCA_HOST_ROOT='/home/box'" in text
    assert "LCA_HOST_OUTPUTS=" in text
    assert "LCA_HOST_GUEST_ROOT=" not in text
