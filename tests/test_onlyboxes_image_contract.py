"""Onlyboxes images must satisfy GuestLayout.onlyboxes() — no /workspace drift."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR
from lca.layer0_infra.sandbox.paths import ONLYBOXES

_REPO = Path(__file__).resolve().parents[1]
_ONLYBOXES = _REPO / "deploy" / "onlyboxes"


def _dockerfile(name: str) -> str:
    return (_ONLYBOXES / name).read_text(encoding="utf-8")


def test_guest_layout_contract_is_frozen() -> None:
    assert ONLYBOXES.root == SANDBOX_MOUNT_ROOT
    assert ONLYBOXES.outputs_dir == f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}"


def test_terminal_image_establishes_guest_root() -> None:
    df = _dockerfile("Dockerfile.terminal")
    assert f"WORKDIR {SANDBOX_MOUNT_ROOT}" in df
    assert f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}" in df
    assert "WORKDIR /workspace" not in df


def test_python_image_establishes_guest_root() -> None:
    df = _dockerfile("Dockerfile.python")
    assert f"WORKDIR {SANDBOX_MOUNT_ROOT}" in df
    assert f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}" in df
    assert "WORKDIR /workspace" not in df


def test_build_scripts_verify_guest_layout() -> None:
    for name in ("build-terminal-image.sh", "build-python-image.sh"):
        text = (_ONLYBOXES / name).read_text(encoding="utf-8")
        assert "smoke-guest-layout.sh" in text
