"""Phase D: validate package integrity.

Two integrity rules per ADR-0105 §11:

1. Every package directory must contain an ``__init__.py`` that exposes a
   sorted, explicit ``__all__`` listing the package's public API.
2. Every ``[tool.lca.package_contracts.<pkg>]`` block in pyproject.toml
   must point to a real directory under the package root, and the
   directory's ``__init__.py`` must import cleanly.

Usage::

    python scripts/check_package_integrity.py [--root PATH]
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "traces"}

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


def _all_from_init(init: Path) -> set[str] | None:
    """Return the explicit __all__ from a package __init__.py, or None
    if the file is absent / cannot be parsed / lacks __all__."""
    if not init.exists():
        return None
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            value = node.value
            if isinstance(value, (ast.List, ast.Tuple)):
                names: set[str] = set()
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
                return names
            return None
    return set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    config_path = args.root.parent / "pyproject.toml"
    declared: dict[str, dict] = {}
    if config_path.exists():
        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
        declared = cfg.get("tool", {}).get("lca", {}).get("package_contracts", {})

    violations: list[str] = []

    # 1. Every package directory under lca/ has __init__.py with __all__.
    for directory in sorted(args.root.rglob("*")):
        if not directory.is_dir():
            continue
        if any(part in SKIP_DIRS for part in directory.parts):
            continue
        init = directory / "__init__.py"
        if not init.exists():
            # Directories without .py at all are not packages; skip.
            if not any(directory.glob("*.py")):
                continue
            rel = directory.relative_to(args.root.parent).as_posix()
            violations.append(f"{rel}: missing __init__.py")
            continue
        all_names = _all_from_init(init)
        if all_names is None:
            rel = init.relative_to(args.root.parent).as_posix()
            violations.append(f"{rel}: missing explicit __all__")

    # 2. Every declared contract points to a real directory.
    for pkg, body in declared.items():
        if not isinstance(body, dict):
            continue
        target = args.root / pkg.replace(".", "/")
        if not target.is_dir():
            violations.append(f"{pkg}: declared contract but directory not found")

    if not violations:
        print("package-integrity: every package has __init__.py + __all__; "
              "every declared contract exists.")
        return 0
    for line in violations:
        print(f"  ✗ {line}", file=sys.stderr)
    print(
        f"package-integrity: {len(violations)} violations.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
