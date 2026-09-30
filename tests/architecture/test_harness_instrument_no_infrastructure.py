"""Structural guard: ``instrument`` wrap package must not import infrastructure.

Theme 2.3 layering fix: ``lca.harness`` depends only on ``lca.contracts``,
so the phase-graph instrument package must never reach into
``lca.infrastructure`` for spine ports/records. The spine types it needs
(``EventSpine`` / ``SpanContext`` / ``SpineContext`` / ``Channel`` /
``Outcome`` / ``is_session_ssot_hook_active``) all live in
``lca.contracts.observability``.
"""

from __future__ import annotations

import ast
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_INSTRUMENT_DIR = _REPO_ROOT / "lca/harness/declarative/compile/instrument"


def _imported_modules(file_path: pathlib.Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_instrument_wrap_has_no_infrastructure_import() -> None:
    """wrap.py 不得 import ``lca.infrastructure``。"""
    wrap_path = _INSTRUMENT_DIR / "wrap.py"
    assert wrap_path.exists(), f"Missing file: {wrap_path}"
    violations = [
        imp
        for imp in _imported_modules(wrap_path)
        if imp == "lca.infrastructure" or imp.startswith("lca.infrastructure.")
    ]
    assert not violations, f"{wrap_path} 仍 import infrastructure: {violations}"


def test_instrument_package_has_no_infrastructure_import() -> None:
    """instrument 包内所有模块均不得 import ``lca.infrastructure``。"""
    assert _INSTRUMENT_DIR.exists(), f"Missing package: {_INSTRUMENT_DIR}"
    violations: list[str] = []
    for py_file in sorted(_INSTRUMENT_DIR.glob("*.py")):
        for imp in _imported_modules(py_file):
            if imp == "lca.infrastructure" or imp.startswith("lca.infrastructure."):
                violations.append(f"{py_file}: imports '{imp}'")
    assert not violations, "instrument 包发现 infrastructure import:\n" + "\n".join(violations)


__all__ = [
    "test_instrument_package_has_no_infrastructure_import",
    "test_instrument_wrap_has_no_infrastructure_import",
]
