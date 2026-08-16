"""Guards against reintroducing Harness composition shortcuts."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_command_gateway_does_not_import_concrete_runtime_layers() -> None:
    imports = _imports(ROOT / "lca/harness/command/gateway.py")
    forbidden = ("lca.layer1_cognitive", "lca.layer2_runtime", "lca.layer3_agent")
    assert not any(module.startswith(forbidden) for module in imports)


def test_legacy_run_carrier_has_no_dsh_special_case() -> None:
    source = (ROOT / "gateway/runs/execute.py").read_text(encoding="utf-8")
    assert "is_dsh_driver" not in source
    assert "execute_dsh_session" not in source
    assert "DEFAULT_RUN_DRIVERS.resolve" in source


def test_all_first_party_plugins_declare_a_manifest() -> None:
    for init_file in (ROOT / "lca/plugins").glob("*/__init__.py"):
        source = init_file.read_text(encoding="utf-8")
        assert "PluginManifest" in source, f"{init_file.parent.name} has no PluginManifest"


def test_session_spine_registers_skills_projection() -> None:
    source = (ROOT / "gateway/spine.py").read_text(encoding="utf-8")
    assert "projections.register(SkillsProjection())" in source
