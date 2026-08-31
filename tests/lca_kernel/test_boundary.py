"""Kernel/transport boundary test — kernel must have ZERO transport framework knowledge.

ADR-0115 决定 3:``lca_kernel/`` cannot import any ASGI framework, HTTP/WS
client library, or the legacy ``gateway/`` directory. ``transport`` is
allowed as a generic English word in docstrings and as a parameter name
(``register_transport`` is the ShutdownCoordinator API); only literal
``import`` statements of forbidden modules are gated.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

LCA_KERNEL_DIR = Path(__file__).resolve().parent.parent.parent / "lca_kernel"

# Frameworks / clients that prove transport knowledge — must never appear
# in any import statement under lca_kernel/.
FORBIDDEN_IMPORTS = {
    "starlette",
    "fastapi",
    "uvicorn",
    "httpx",
    "aiohttp",
    "websockets",
    "hypercorn",
    "granian",
    "lca.infrastructure.transport",  # the legacy transport adapter module
    "gateway",  # the legacy gateway/ physical package
    "lca.plugins.transport",  # transport plugin namespace (PR-4 territory)
}


def _scan_python_files() -> list[Path]:
    return sorted(LCA_KERNEL_DIR.glob("*.py"))


def _imports_in(path: Path) -> list[ast.stmt]:
    """Return all top-level ``Import`` / ``ImportFrom`` statements."""
    tree = ast.parse(path.read_text())
    return [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]


def _modules_in_stmt(stmt: ast.stmt) -> list[str]:
    """Flatten ``import x, y`` / ``from x import y`` to module names."""
    names: list[str] = []
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            names.append(alias.name)
    elif isinstance(stmt, ast.ImportFrom) and stmt.module is not None:
        names.append(stmt.module)
    return names


def _violating_imports(path: Path) -> list[str]:
    out: list[str] = []
    for stmt in _imports_in(path):
        for mod in _modules_in_stmt(stmt):
            for forbidden in FORBIDDEN_IMPORTS:
                if mod == forbidden or mod.startswith(forbidden + "."):
                    out.append(f"{type(stmt).__name__} {mod}")
                    break
    return out


@pytest.mark.parametrize("py_file", _scan_python_files(), ids=lambda p: p.name)
def test_no_transport_framework_imports(py_file: Path) -> None:
    """No kernel module imports transport / ASGI / framework / gateway."""
    viols = _violating_imports(py_file)
    assert not viols, f"{py_file.name} imports forbidden module(s): {viols}"


def test_kernel_directory_has_no_transport_subdir() -> None:
    forbidden_dirs = {"transport", "webserver", "http"}
    for sub in LCA_KERNEL_DIR.iterdir():
        if sub.is_dir():
            assert sub.name not in forbidden_dirs, (
                f"lca_kernel/ contains forbidden subdirectory {sub.name}"
            )


def test_kernel_module_count_is_at_most_13() -> None:
    """ADR-0115 §决定 1 锁定的文件数上限(13)。"""
    py_files = list(LCA_KERNEL_DIR.glob("*.py"))
    assert len(py_files) <= 13, f"expected ≤13 files, got {len(py_files)}"


def test_kernel_modules_have_no_module_level_singletons() -> None:
    """ADR-0062 + ADR-0115 决定 9:no module-level singletons in kernel.

    Module-level singletons look like ``_SOMETHING = SomeSingleton(...)`` at
    the top level outside functions / classes / TYPE_CHECKING blocks. We
    inspect parsed AST so docstrings and comments don't trigger false
    positives.
    """
    for py_file in _scan_python_files():
        tree = ast.parse(py_file.read_text())
        for node in tree.body:
            # Skip annotated assignments used as type aliases.
            if isinstance(node, ast.AnnAssign):
                continue
            # Module-level function / class definitions are not singletons.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            # Imports are explicitly allowed at module level.
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id.startswith("_")
                        and target.id.isupper()
                        and len(target.id) > 2
                    ):
                        pytest.fail(
                            f"{py_file.name}: module-level singleton "
                            f"assignment violates ADR-0062: {ast.dump(node)}",
                        )
