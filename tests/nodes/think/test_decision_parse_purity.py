"""Test AST purity and execution independence of think.decision.parse."""

import ast
from pathlib import Path


def test_think_decision_parse_has_no_runtime_plane_imports():
    """Verify think.decision.parse does not import from infrastructure.runtime_plane."""
    file_path = Path("lca/nodes/think/decision/parse.py")
    assert file_path.exists(), f"{file_path} not found"

    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    for mod in imported_modules:
        assert not mod.startswith(
            "lca.infrastructure.runtime_plane"
        ), f"Forbidden cross-layer import in think node: {mod}"
