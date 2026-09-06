"""ADR-0194 §9 / ADR-0195 §9 acceptance guards (P5-07 / P5-08)."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "lca" / "plugins"
BUNDLES = ROOT / "bundles"
BUNDLE = BUNDLES / "declarative-phase-graph.yaml"
WEB_APP_BUNDLE = BUNDLES / "web-app.yaml"
SESSION_RUNTIME_BUNDLE = BUNDLES / "session-runtime.yaml"

_STANDARD_PHASES = ("perceive", "think", "act", "reflect", "remember", "stop")
_DECLARATIVE_BUNDLE_PATHS = (
    BUNDLE,
    BUNDLES / "declarative-recovery.yaml",
)

# COMPAT(owner: ADR-0194, delete-when: declarative bundles have zero phase_graph $module).
# Use nested module paths (e.g. phase_graph.stop.policy), not flat (phase_graph.stop_policy).
_ALLOWED_DECLARATIVE_PHASE_GRAPH_MODULES: frozenset[str] = frozenset()

# rg-equivalent baseline; decrease intentionally → lower constant + note in PR.
_WEB_APP_PHASE_GRAPH_MODULE_BASELINE = 0


def _extract_module_path(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "$module:" not in stripped:
        return None
    _, _, value = stripped.partition("$module:")
    return value.strip()


def _phase_graph_module_lines(bundle_path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(bundle_path.read_text(encoding="utf-8").splitlines(), start=1):
        module = _extract_module_path(line)
        if module is not None and "phase_graph" in module:
            hits.append((lineno, module))
    return hits


def _count_phase_graph_module_lines(bundle_path: Path) -> int:
    return len(_phase_graph_module_lines(bundle_path))


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

    def test_no_flat_phase_graph_in_declarative_bundle(self) -> None:
        """Six standard executors must bind loop.phase.*, not legacy phase_graph paths."""
        text = BUNDLE.read_text(encoding="utf-8")
        for phase in _STANDARD_PHASES:
            assert f"lca.plugins.loop.phase.{phase}.standard.plugin" in text
            assert f"lca.plugins.phase_graph.{phase}" not in text
            assert f"lca.plugins.phase_graph.standard.{phase}" not in text

    def test_declarative_bundle_no_legacy_phase_graph_modules(self) -> None:
        """declarative-phase-graph + declarative-recovery: zero phase_graph $module (or COMPAT allowlist)."""
        offenders: list[str] = []
        for bundle_path in _DECLARATIVE_BUNDLE_PATHS:
            rel = bundle_path.relative_to(ROOT).as_posix()
            for lineno, module in _phase_graph_module_lines(bundle_path):
                if module in _ALLOWED_DECLARATIVE_PHASE_GRAPH_MODULES:
                    continue
                offenders.append(f"{rel}:{lineno}: {module}")
        assert not offenders, (
            "declarative bundles must not load legacy phase_graph modules:\n"
            + "\n".join(offenders)
            + "\nIf migration-compat, add nested path to _ALLOWED_DECLARATIVE_PHASE_GRAPH_MODULES."
        )

    def test_web_app_phase_graph_module_count_does_not_increase(self) -> None:
        """web-app.yaml phase_graph $module debt must not grow during loop seam migration."""
        current = _count_phase_graph_module_lines(WEB_APP_BUNDLE)
        assert current <= _WEB_APP_PHASE_GRAPH_MODULE_BASELINE, (
            f"web-app.yaml phase_graph $module count increased: {current} > "
            f"baseline {_WEB_APP_PHASE_GRAPH_MODULE_BASELINE}. "
            "Migrate to loop seam nested paths; if count dropped, lower the baseline."
        )

    def test_web_app_phase_graph_module_baseline_is_current(self) -> None:
        """Prevent baseline drift without intentional migration progress."""
        current = _count_phase_graph_module_lines(WEB_APP_BUNDLE)
        assert current == _WEB_APP_PHASE_GRAPH_MODULE_BASELINE, (
            f"web-app.yaml phase_graph $module count is {current}; "
            f"update _WEB_APP_PHASE_GRAPH_MODULE_BASELINE from "
            f"{_WEB_APP_PHASE_GRAPH_MODULE_BASELINE} when migration reduces debt."
        )

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

    def test_no_lca_fact_gateway_in_production(self) -> None:
        """P5-01: rollback env flag removed from production paths."""
        proc = subprocess.run(
            ["rg", "-l", "LCA_FACT_GATEWAY", "lca/"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, f"LCA_FACT_GATEWAY still in production: {proc.stdout}"

    def test_no_spine_reflector_plugins_in_bundles(self) -> None:
        """P2-16 / P5: bundle entries must not load spine_reflector_* publisher modules."""
        offenders: list[str] = []
        for bundle_path in sorted(BUNDLES.glob("*.yaml")):
            for lineno, line in enumerate(bundle_path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "$module:" in stripped and "spine_reflector" in stripped:
                    rel = bundle_path.relative_to(ROOT).as_posix()
                    offenders.append(f"{rel}:{lineno}: {stripped}")
        assert not offenders, "spine_reflector bundle entries remain:\n" + "\n".join(offenders)


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

    def test_session_runtime_bundle_modules_loadable(self) -> None:
        """P5-02: session-runtime.yaml $module paths import and expose setup."""
        modules: list[str] = []
        for line in SESSION_RUNTIME_BUNDLE.read_text(encoding="utf-8").splitlines():
            module = _extract_module_path(line)
            if module is not None and module.startswith("lca.plugins.session."):
                modules.append(module)
        assert len(modules) >= 11, f"expected session bundle entries, got {modules!r}"
        for module_path in modules:
            mod = importlib.import_module(module_path)
            assert hasattr(mod, "setup"), f"{module_path} missing setup"
