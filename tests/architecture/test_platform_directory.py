"""Architecture tests for platform directory layout (ADR-0195 P0)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LCA = ROOT / "lca"
PLUGINS = LCA / "plugins"

REQUIRED_LCA_TOP = frozenset(
    {
        "agent",
        "application",
        "cognition",
        "contracts",
        "harness",
        "infrastructure",
        "loop",
        "plugins",
        "runtime",
        "session",
    }
)

SEAM_TREE_ANCHORS = ("cognitive", "loop", "observability", "transport", "domain", "composition", "meta")


class TestPlatformDirectory:
    def test_lca_top_level_packages(self) -> None:
        actual = {p.name for p in LCA.iterdir() if p.is_dir() and not p.name.startswith("_")}
        assert actual >= REQUIRED_LCA_TOP, f"missing packages: {sorted(REQUIRED_LCA_TOP - actual)}"

    def test_session_and_loop_packages_exist(self) -> None:
        assert (LCA / "session" / "README.md").is_file()
        assert (LCA / "loop" / "README.md").is_file()

    def test_platform_spec_exists(self) -> None:
        assert (ROOT / "docs/specs/platform-directory-architecture.md").is_file()

    def test_plugins_architecture_doc_exists(self) -> None:
        assert (PLUGINS / "ARCHITECTURE.md").is_file()

    @pytest.mark.parametrize("anchor", SEAM_TREE_ANCHORS)
    def test_seam_tree_anchor_readme(self, anchor: str) -> None:
        readme = PLUGINS / anchor / "README.md"
        assert readme.is_file(), f"missing seam anchor README: {anchor}"

    def test_harness_graph_and_composition_readme(self) -> None:
        assert (LCA / "harness" / "graph" / "README.md").is_file()
        assert (LCA / "harness" / "composition" / "README.md").is_file()

    def test_no_spine_reflector_plugin_dirs_remain(self) -> None:
        """P5-01: spine_reflector_* publisher dirs deleted."""
        publishers = PLUGINS / "events" / "publishers"
        if not publishers.is_dir():
            pytest.skip("no events/publishers")
        reflectors = [
            d.name
            for d in publishers.iterdir()
            if d.is_dir() and d.name.startswith("spine_reflector")
        ]
        assert reflectors == []

    def test_check_platform_directory_script_passes_hard_gates(self) -> None:
        import subprocess

        proc = subprocess.run(
            ["uv", "run", "python", "scripts/check_platform_directory.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
