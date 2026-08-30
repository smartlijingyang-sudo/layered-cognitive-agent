"""Phase D: enforce the §11 rule that no package exceeds 8 .py files.

The cap (excluding __init__.py) keeps each subdirectory focused on one
domain. Per ADR-0105 §11.x, exempt files live in
``[tool.lca.package_contracts.<pkg>].filename_whitelist`` (currently
none, but the hook is wired so future exempts can register here).

Usage::

    python scripts/check_package_size.py [--root PATH] [--max N]
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "traces"}


def _load_whitelist() -> dict[str, list[str]]:
    """Load [tool.lca.package_contracts.<pkg>].filename_whitelist from pyproject.toml."""
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.exists():
        return {}
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    result: dict[str, list[str]] = {}
    for pkg, cfg in contracts.items():
        if "filename_whitelist" in cfg:
            result[pkg] = list(cfg["filename_whitelist"])
    return result


def _walk(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_dir():
            continue
        py_files = [
            p for p in path.iterdir()
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
        ]
        if py_files:
            yield path, len(py_files)


def _rel_package(absolute_dir: Path, root: Path) -> str:
    """Convert /abs/path/lca/foo/bar to lca.foo.bar."""
    rel = absolute_dir.relative_to(root)
    return ".".join(rel.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    parser.add_argument("--max", type=int, default=8)
    args = parser.parse_args(argv)

    whitelist = _load_whitelist()

    violations: list[tuple[Path, int, int]] = []
    for directory, count in _walk(args.root):
        pkg = _rel_package(directory, args.root)
        # Subtract whitelisted files
        wl = whitelist.get(pkg, [])
        if wl:
            count -= len(wl)
        if count > args.max:
            violations.append((directory, count, count + len(wl)))

    if not violations:
        print(f"package-size: every .py package ≤ {args.max} files (under {args.root}).")
        return 0
    for path, count, raw in violations:
        rel = path.relative_to(args.root)
        print(f"  ✗ {rel}: {count} files (cap {args.max}, {raw} raw w/o whitelist)", file=sys.stderr)
    print(
        f"package-size: {len(violations)} package(s) exceed {args.max}-file cap. "
        "Move overflowing .py into a sibling subpackage or register an exempt in "
        "pyproject.toml `[tool.lca.package_contracts.<pkg>].filename_whitelist`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())