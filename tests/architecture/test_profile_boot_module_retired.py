"""Structural guard: the deprecated harness boot shim stays retired.

ADR-0195 P4-K02 moved boot to ``lca_kernel``. The compat module
``lca/harness/profile/boot/boot.py`` must never come back: no production or
test module may import ``lca.harness.profile.boot.boot`` anymore.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETIRED_MODULE = "lca.harness.profile.boot.boot"
SCAN_ROOTS = (REPO / "lca", REPO / "lca_kernel", REPO / "tests", REPO / "scripts")


def _module_names(tree: ast.AST) -> list[str]:
    """Flatten ``import x`` / ``from x import y`` to referenced module names."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def _python_files() -> list[Path]:
    return sorted(path for root in SCAN_ROOTS if root.is_dir() for path in root.rglob("*.py"))


def test_deprecated_boot_module_file_is_deleted() -> None:
    assert not (REPO / "lca/harness/profile/boot/boot.py").exists()


def test_no_module_imports_the_retired_boot_shim() -> None:
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for mod in _module_names(tree):
            if mod == RETIRED_MODULE or mod.startswith(RETIRED_MODULE + "."):
                violations.append(f"{path.relative_to(REPO).as_posix()}: {mod}")
    assert not violations, (
        "lca.harness.profile.boot.boot is retired; import lca_kernel instead:\n"
        + "\n".join(violations)
    )
