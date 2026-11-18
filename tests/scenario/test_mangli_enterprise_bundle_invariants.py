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


def test_mangli_profile_resolves_cleanly():
    profile_path = Path("profiles/mangli-enterprise.yaml")
    assert profile_path.exists(), f"Profile not found: {profile_path}"
    resolved = resolve_profile(profile_path)
    # 检验 ResolvedProfile.plugins 数据契约
    plugin_ids = {p.id for p in resolved.plugins}
    assert "mangli-enterprise-playground-route" in plugin_ids
    assert "lca-webserver-router" in plugin_ids
