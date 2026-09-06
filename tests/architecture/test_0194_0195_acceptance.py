"""ADR-0194 §9 / ADR-0195 §9 acceptance guards (P5-07 / P5-08)."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "lca" / "plugins"
BUNDLE = ROOT / "bundles" / "declarative-phase-graph.yaml"


class TestADR0194Acceptance:
    """Executable subset of ADR-0194 §9 Overall Done criteria."""

    def test_loop_readme_and_phase_bundle_exist(self) -> None:
        assert (ROOT / "lca" / "loop" / "README.md").is_file()
        assert BUNDLE.is_file()

    def test_standard_phase_executors_in_loop_seam(self) -> None:
        phases = ("perceive", "think", "act", "reflect", "remember", "stop")
        for phase in phases:
            plugin_py = PLUGINS / "loop" / "phase" / phase / "standard" / "plugin.py"
            assert plugin_py.is_file(), f"missing {plugin_py}"
            source = plugin_py.read_text(encoding="utf-8")
            assert "@plugin(" in source
            assert "PhaseExecutor" in source or "execute" in source

    def test_bundle_points_at_loop_phase_not_phase_graph(self) -> None:
        text = BUNDLE.read_text(encoding="utf-8")
        for phase in ("perceive", "think", "act", "reflect", "remember", "stop"):
            assert f"lca.plugins.loop.phase.{phase}.standard.plugin" in text
            assert f"lca.plugins.phase_graph.{phase}" not in text

    def test_control_slots_in_loop_seam(self) -> None:
        text = BUNDLE.read_text(encoding="utf-8")
        assert "lca.plugins.loop.control." in text
        assert "lca.plugins.control_contributions." not in text

    def test_cognition_no_spine_reflector_import(self) -> None:
        proc = subprocess.run(
            [
                "rg",
                "-l",
                "spine_reflector",
                "lca/cognition/",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, f"cognition imports reflector: {proc.stdout}"


class TestADR0195Acceptance:
    """Executable subset of ADR-0195 §9 Platform Done criteria."""

    @pytest.mark.parametrize(
        "readme",
        [
            "lca_kernel/README.md",
            "lca/loop/README.md",
            "lca/plugins/transport/README.md",
            "lca/plugins/README.md",
        ],
    )
    def test_platform_readme_anchors(self, readme: str) -> None:
        assert (ROOT / readme).is_file()

    def test_seam_tree_anchors_have_readme(self) -> None:
        for anchor in ("cognitive", "loop", "domain", "composition"):
            assert (PLUGINS / anchor / "README.md").is_file()

    def test_loop_driver_and_reducer_migrated(self) -> None:
        for rel in ("loop/driver/plugin.py", "loop/reducer/plugin.py"):
            path = PLUGINS / rel
            assert path.is_file()
            assert "@plugin(" in path.read_text(encoding="utf-8")

    def test_cognitive_gate_service_loadable(self) -> None:
        mod = importlib.import_module("lca.plugins.cognitive.gate.service.plugin")
        assert hasattr(mod, "setup")

    def test_domain_assistant_catalog_loadable(self) -> None:
        mod = importlib.import_module("lca.plugins.domain.assistant.catalog.plugin")
        assert hasattr(mod, "setup")
