"""Execution-environment picker patch: 用电脑 / 云沙箱 / 自动."""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.lobehub.patches.ui.execution_target import _patch_switcher

_SWITCHER = Path("lobehub-ui/src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx")
_UPSTREAM_SWITCHER = Path(".lobehub-upstream/src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx")
_CUSTOMIZATIONS = Path("deploy/lobehub/CUSTOMIZATIONS.md")


def test_patch_drops_none_and_download_desktop() -> None:
    src_file = _UPSTREAM_SWITCHER if _UPSTREAM_SWITCHER.is_file() else _SWITCHER
    if not src_file.is_file():
        pytest.skip("Neither upstream nor lobehub-ui switcher is present")
    from deploy.lobehub.patches.ui.execution_target import _patch_imports

    patched = _patch_switcher(_patch_imports(src_file.read_text(encoding="utf-8")))
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


def test_patch_unblocks_offline_devices_and_strips_code_input() -> None:
    src_file = _UPSTREAM_SWITCHER if _UPSTREAM_SWITCHER.is_file() else _SWITCHER
    if not src_file.is_file():
        pytest.skip("Neither upstream nor lobehub-ui switcher is present")
    from deploy.lobehub.patches.ui.execution_target import (
        _patch_imports,
        _patch_pairing_jsx,
        _patch_pairing_state,
        _patch_styles,
        _patch_switcher,
    )

    text = src_file.read_text(encoding="utf-8")
    text = _patch_imports(text)
    text = _patch_styles(text)
    text = _patch_switcher(text)
    text = _patch_pairing_state(text)
    patched = _patch_pairing_jsx(text)

    # Invariant 1: 离线设备不再包含 disabled={!d.online}
    assert "disabled={!d.online}" not in patched
    # Invariant 2: 主视图彻底无手动输码输入框
    assert "className={styles.pairingInput}" not in patched
    # Invariant 3: 包含一键下载并启动
    assert "一键下载并启动" in patched
    assert "runner.bat" in patched
    assert "CopyButton" in patched
