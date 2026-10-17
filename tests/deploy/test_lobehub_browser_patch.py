"""Tests for LobeHub browser preview card and viewer drawer UI patches (INV-BROWSER-06)."""

import subprocess
import sys

from lca.contracts.models.browser.stream import normalize_viewport_coordinates


def test_browser_coordinate_normalization_inv_browser_06():
    """INV-BROWSER-06: 归一化视口坐标严格保持在 [0.0, 1.0] 区间内，且处理浮点与拉伸精度。"""
    # 居中点击
    nx, ny = normalize_viewport_coordinates(640.0, 400.0, 1280.0, 800.0)
    assert nx == 0.5
    assert ny == 0.5

    # 左上角
    nx, ny = normalize_viewport_coordinates(0.0, 0.0, 1280.0, 800.0)
    assert nx == 0.0
    assert ny == 0.0

    # 右下角
    nx, ny = normalize_viewport_coordinates(1280.0, 800.0, 1280.0, 800.0)
    assert nx == 1.0
    assert ny == 1.0

    # 越界防溢出截断 (Clamping)
    nx, ny = normalize_viewport_coordinates(-10.0, 900.0, 1280.0, 800.0)
    assert nx == 0.0
    assert ny == 1.0

    # 视口为 0 容错
    nx, ny = normalize_viewport_coordinates(50.0, 50.0, 0.0, 0.0)
    assert nx == 0.0
    assert ny == 0.0


def test_browser_patches_registered_in_engine():
    res = subprocess.run(
        [sys.executable, "deploy/lobehub/patch_lobehub.py", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "browser_preview_card" in res.stdout
    assert "browser_viewer_drawer" in res.stdout
