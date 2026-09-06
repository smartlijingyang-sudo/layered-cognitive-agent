"""Architecture tests for cognitive directory discipline (ADR-0195 extension)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ANCHOR_ROOTS = (
    "lca/harness",
    "lca/cognition",
    "lca/loop",
    "lca/session",
)

MAX_DIRECT_PY = 5


def _direct_py_count(directory: Path) -> int:
    return sum(
        1
        for p in directory.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name not in ("__init__.py", "__main__.py")
    )


class TestCognitiveDirectoryDiscipline:
    def test_spec_exists(self) -> None:
        assert (ROOT / "docs/specs/cognitive-directory-discipline.md").is_file()

    def test_anchors_config_exists(self) -> None:
        assert (ROOT / "scripts/cognitive_directory_anchors.toml").is_file()

    @pytest.mark.parametrize("anchor", ANCHOR_ROOTS)
    def test_anchor_root_file_budget(self, anchor: str) -> None:
        root = ROOT / anchor
        count = _direct_py_count(root)
        assert count <= MAX_DIRECT_PY, f"{anchor}/ has {count} direct .py (max {MAX_DIRECT_PY})"

    def test_check_cognitive_directory_passes_full_tree(self) -> None:
        proc = subprocess.run(
            ["uv", "run", "python", "scripts/check_cognitive_directory.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout

    def test_loop_emit_and_commit_subpackages_exist(self) -> None:
        assert (ROOT / "lca/loop/emit/spine/ep.py").is_file()
        assert (ROOT / "lca/loop/commit/act_journal.py").is_file()

    def test_harness_plugin_subpackage_exists(self) -> None:
        plugin = ROOT / "lca/harness/plugin"
        assert plugin.is_dir()
        assert _direct_py_count(plugin) <= MAX_DIRECT_PY

    def test_session_lifecycle_subpackage_exists(self) -> None:
        lifecycle = ROOT / "lca/session/lifecycle"
        assert lifecycle.is_dir()
        assert _direct_py_count(lifecycle) <= MAX_DIRECT_PY
