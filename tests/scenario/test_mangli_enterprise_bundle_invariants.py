"""Tests for Mangli enterprise bundle and profile invariants, and zero-mutation guard (INV-07)."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 跨平台兼容：在 Windows 下为缺失的 fcntl 注入 mock，使 profile resolve 顺利通过
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        mock_fcntl = MagicMock()
        mock_fcntl.LOCK_EX = 2
        mock_fcntl.LOCK_UN = 8
        sys.modules["fcntl"] = mock_fcntl

from lca.harness.profile.resolve.resolve import resolve_profile


def test_core_zero_mutation_against_merge_base():
    cmd = [
        "git",
        "diff",
        "--name-only",
        "origin/main...HEAD",
        "--",
        "lca/contracts",
        "lca/cognition",
        "lca/runtime",
        "lca/loop",
        "lca/framework",
        "lca_kernel",
        "vendor",
    ]
    res = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, check=True
    )
    assert res.stdout.strip() == "", (
        f"Core files were mutated against origin/main:\n{res.stdout}"
    )


PLAYGROUND_PLUGIN_ID = "mangli-enterprise-playground-route"


def _resolved_plugin_ids(profile_path: Path) -> set[str]:
    assert profile_path.exists(), f"Profile not found: {profile_path}"
    resolved = resolve_profile(profile_path)
    return {p.id for p in resolved.plugins}


def test_mangli_profile_resolves_cleanly():
    plugin_ids = _resolved_plugin_ids(Path("profiles/mangli-enterprise.yaml"))
    assert "lca-webserver-router" in plugin_ids


def test_production_profile_excludes_playground_proxy():
    """生产装配不得包含 /playground。

    playground 插件带一个免鉴权、可指定转发目标的 HTTP/WS 代理（经网关联调
    通道），一旦进入生产就等于把服务器变成开放转发器。这条断言是它唯一的
    安全边界 —— 删掉它等于允许代理上线。
    """
    plugin_ids = _resolved_plugin_ids(Path("profiles/mangli-enterprise.yaml"))
    assert PLAYGROUND_PLUGIN_ID not in plugin_ids


def test_dev_profile_includes_playground_console():
    """联调 profile 必须能打开 /playground，否则经网关测试无从进行。"""
    plugin_ids = _resolved_plugin_ids(Path("profiles/mangli-enterprise-dev.yaml"))
    assert PLAYGROUND_PLUGIN_ID in plugin_ids
    assert "lca-webserver-router" in plugin_ids
