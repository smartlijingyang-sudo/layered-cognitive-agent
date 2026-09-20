"""ADR-0246 M1 架构不变量：依赖方向守护。"""

from __future__ import annotations

import ast
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# ADR-0246 M1 contracts files
_M1_CONTRACTS_FILES = [
    _REPO_ROOT / "lca/contracts/models/core/execution/local_exec.py",
    _REPO_ROOT / "lca/contracts/models/core/state/plane.py",
    _REPO_ROOT / "lca/contracts/protocols/runtime/infra/infra.py",
]


def _get_imports(file_path: pathlib.Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_m1_contracts_do_not_import_infrastructure() -> None:
    """contracts 层不得反向 import infrastructure（C1/C2 不变量）。"""
    violations = []
    for py_file in _M1_CONTRACTS_FILES:
        assert py_file.exists(), f"Missing file: {py_file}"
        imports = _get_imports(py_file)
        for imp in imports:
            if imp.startswith("lca.infrastructure"):
                violations.append(f"{py_file}: imports '{imp}'")
    assert not violations, "M1 contracts 发现反向 import:\n" + "\n".join(violations)


def test_fake_providers_not_imported_in_production() -> None:
    """fake providers 不得被生产代码 import。"""
    prod_dirs = [
        _REPO_ROOT / "lca/infrastructure/computer/machine",
        _REPO_ROOT / "lca/infrastructure/computer/sandbox",
        _REPO_ROOT / "lca/cognition",
    ]
    violations = []
    for d in prod_dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            if "computer.fake" in source or "FakeCompanionProvider" in source:
                violations.append(str(py_file))
    assert not violations, "生产代码不得 import fake providers:\n" + "\n".join(violations)
