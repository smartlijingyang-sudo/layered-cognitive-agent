"""Execution-environment picker patch: 用电脑 / 云沙箱 / 自动."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.patches.ui.execution_target import _patch_switcher

_SWITCHER = Path("lobehub-ui/src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx")
_CUSTOMIZATIONS = Path("deploy/lobehub/CUSTOMIZATIONS.md")


def test_patch_drops_none_and_download_desktop() -> None:
    patched = _patch_switcher(_SWITCHER.read_text(encoding="utf-8"))
    assert "LCA: sidecar is use-computer" in patched
    assert "handleSelect('none')" not in patched
    assert "downloadDesktop" not in patched
    assert "DOWNLOAD_URL" not in patched
    assert "handleSelect('local')" in patched
    assert "handleSelect('auto')" in patched
    assert "handleSelect('sandbox')" in patched
    assert (
        "isDesktop ?"
        not in patched.split("label={t('heteroAgent.executionTarget.local')}")[0][-80:]
    )


def test_customizations_lists_patch() -> None:
    assert "`execution_target`" in _CUSTOMIZATIONS.read_text(encoding="utf-8")
