#!/usr/bin/env python3
"""Rename files that repeat parent directory prefix (cognitive-directory §4.1).

Example: delegation/delegation_cache.py -> delegation/cache.py

Usage:
    uv run python scripts/rename_redundant_prefixes.py --dry-run
    uv run python scripts/rename_redundant_prefixes.py --apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = frozenset({"__pycache__", ".git", ".venv", "vendor", "tests"})


def _candidates(root: Path) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for path in root.rglob("*.py"):
        if any(p in SKIP for p in path.parts) or path.name in ("__init__.py", "__main__.py"):
            continue
        parent_name = path.parent.name
        stem = path.stem
        prefix = f"{parent_name}_"
        if stem.startswith(prefix) and len(stem) > len(prefix):
            new_name = stem[len(prefix) :] + ".py"
            dst = path.parent / new_name
            if dst.exists():
                continue
            moves.append((path, dst))
    return moves


def _rewrite_imports(mapping: dict[str, str]) -> int:
    sorted_old = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    changed = 0
    for base in (ROOT / "lca", ROOT / "lca_kernel", ROOT / "tests", ROOT / "scripts", ROOT / "docs"):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in (".py", ".md", ".toml", ".yaml", ".yml") or any(
                p in SKIP for p in path.parts
            ):
                continue
            text = path.read_text(encoding="utf-8")
            original = text
            for old, new in sorted_old:
                text = re.sub(rf"\bfrom {re.escape(old)} import\b", f"from {new} import", text)
                text = re.sub(rf"\bimport {re.escape(old)}\b", f"import {new}", text)
                text = text.replace(f'"{old}"', f'"{new}"')
                text = text.replace(f"'{old}'", f"'{new}'")
            if text != original:
                path.write_text(text, encoding="utf-8")
                changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--roots", nargs="+", default=["lca", "lca_kernel"])
    args = parser.parse_args()

    moves: list[tuple[Path, Path]] = []
    for name in args.roots:
        root = ROOT / name
        if root.is_dir():
            moves.extend(_candidates(root))

    print(f"rename candidates: {len(moves)}")
    for src, dst in moves[:30]:
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
    if len(moves) > 30:
        print(f"  ... and {len(moves) - 30} more")

    if not args.apply:
        print("\nDRY-RUN — re-run with --apply")
        return 0

    mapping: dict[str, str] = {}
    for src, dst in moves:
        subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT, check=True)
        old_mod = ".".join(src.relative_to(ROOT).with_suffix("").parts)
        new_mod = ".".join(dst.relative_to(ROOT).with_suffix("").parts)
        mapping[old_mod] = new_mod

    n = _rewrite_imports(mapping)
    print(f"\nAPPLIED {len(moves)} renames; updated {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
