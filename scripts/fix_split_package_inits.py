#!/usr/bin/env python3
"""Populate auto-created __init__.py files after directory split.

For each package dir whose __init__.py only contains the split marker,
re-export public symbols from sibling modules (single-module subdirs).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "Auto-created by split_oversized_directories"


def _public_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" and isinstance(node.value, ast.List):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            names.append(elt.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _fix_init(package_dir: Path) -> bool:
    init = package_dir / "__init__.py"
    if not init.is_file():
        return False
    text = init.read_text(encoding="utf-8")
    if MARKER not in text and "split_oversized_directories" not in text:
        return False
    py_files = sorted(
        p for p in package_dir.glob("*.py") if p.name not in ("__init__.py", "__main__.py")
    )
    if len(py_files) != 1:
        return False
    mod = py_files[0]
    mod_name = mod.stem
    names = _public_names(mod)
    if not names:
        return False
    lines = [
        f'"""Public exports for ``{package_dir.name}`` (auto-fixed)."""',
        "",
        f"from {'.'.join(package_dir.relative_to(ROOT).parts)}.{mod_name} import (",
    ]
    for n in names:
        lines.append(f"    {n},")
    lines.append(")")
    lines.append("")
    lines.append(f"__all__ = {names!r}")
    lines.append("")
    init.write_text("\n".join(lines), encoding="utf-8")
    return True


def main() -> int:
    fixed = 0
    for init in ROOT.rglob("__init__.py"):
        if any(p in init.parts for p in (".git", ".venv", "vendor", "node_modules")):
            continue
        if _fix_init(init.parent):
            fixed += 1
            print(f"fixed {init.parent.relative_to(ROOT)}")
    print(f"fixed {fixed} package(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
