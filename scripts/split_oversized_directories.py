#!/usr/bin/env python3
"""Split package directories exceeding max direct .py count.

Reads semantic groups from directory_split_plan.toml; falls back to prefix heuristic.
Updates all Python imports after moves.

Usage:
    uv run python scripts/split_oversized_directories.py --dry-run
    uv run python scripts/split_oversized_directories.py --apply
    uv run python scripts/split_oversized_directories.py --apply --roots lca
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
PLAN = Path(__file__).resolve().parent / "directory_split_plan.toml"
SKIP_DIRS = frozenset({"__pycache__", ".git", ".venv", "vendor", "lobehub-ui", "node_modules"})
SKIP_ROOTS = frozenset({"tests"})  # only when scanning for splits, not import rewrite


def _load_plan() -> dict:
    if not PLAN.is_file():
        return {}
    with PLAN.open("rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if k != "max_per_dir"}


def _direct_py(directory: Path) -> list[Path]:
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name not in ("__init__.py", "__main__.py")
    )


def _module_path(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _plan_groups(plan: dict, directory: Path) -> dict[str, list[str]] | None:
    key = _module_path(directory)
    parts = key.split(".")
    node: object = plan
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            node = None
            break
        node = node[part]
    if not isinstance(node, dict):
        return None
    if not all(isinstance(v, list) for v in node.values()):
        return None
    return {str(k): list(v) for k, v in node.items()}


def _heuristic_groups(files: list[Path], max_per: int) -> dict[str, list[str]]:
    """Cluster by first underscore segment; pack into max_per sized buckets."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for f in files:
        stem = f.stem.lstrip("_")
        key = stem.split("_")[0] if "_" in stem else stem
        if not key:
            key = "internal"
        buckets[key].append(f.name)

    groups: dict[str, list[str]] = {}
    for key, names in sorted(buckets.items()):
        if len(names) <= max_per:
            groups[key] = names
        else:
            for i in range(0, len(names), max_per):
                chunk = names[i : i + max_per]
                groups[f"{key}_{i // max_per + 1}"] = chunk
    return groups


def _collect_moves(max_per: int, roots: list[str], plan: dict) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for root_name in roots:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        directories_to_scan: list[Path] = [root]
        for directory in sorted(root.rglob("*")):
            if directory.is_dir() and not any(p in SKIP_DIRS for p in directory.parts):
                directories_to_scan.append(directory)
        for directory in directories_to_scan:
            files = _direct_py(directory)
            if len(files) <= max_per:
                continue
            groups = _plan_groups(plan, directory)
            if groups is None:
                groups = _heuristic_groups(files, max_per)
            assigned = {n for names in groups.values() for n in names}
            missing = [f for f in files if f.name not in assigned]
            if missing:
                groups.setdefault("_overflow", [])
                for i, f in enumerate(missing):
                    bucket = f"_overflow_{i // max_per}"
                    groups.setdefault(bucket, []).append(f.name)
            for subdir, names in groups.items():
                if not names:
                    continue
                if len(names) > max_per:
                    for i in range(0, len(names), max_per):
                        chunk = names[i : i + max_per]
                        sub = f"{subdir}_{i // max_per}" if i else subdir
                        for name in chunk:
                            src = directory / name
                            dst = directory / sub / name
                            moves.append((src, dst))
                else:
                    for name in names:
                        src = directory / name
                        dst = directory / subdir / name
                        moves.append((src, dst))
    return moves


def _rewrite_imports(moves: list[tuple[Path, Path]]) -> int:
    mapping: dict[str, str] = {}
    for src, dst in moves:
        mapping[_module_path(src)] = _module_path(dst)

    if not mapping:
        return 0

    sorted_old = sorted(mapping, key=len, reverse=True)
    changes = 0
    for base in (ROOT / "lca", ROOT / "lca_kernel", ROOT / "tests", ROOT / "scripts"):
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(p in SKIP_DIRS for p in path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            original = text
            for old in sorted_old:
                new = mapping[old]
                for pat in (
                    rf"\bfrom {re.escape(old)} import\b",
                    rf"\bimport {re.escape(old)}\b",
                    rf'"{re.escape(old)}"',
                    rf"'{re.escape(old)}'",
                ):
                    repl = pat.replace(re.escape(old), new).replace(r"\bfrom ", "from ").replace(r"\bimport ", "import ")
                    if pat.startswith(r"\bfrom"):
                        text = re.sub(rf"\bfrom {re.escape(old)} import\b", f"from {new} import", text)
                    elif pat.startswith(r"\bimport"):
                        text = re.sub(rf"\bimport {re.escape(old)}\b", f"import {new}", text)
                    elif '"' in pat:
                        text = text.replace(f'"{old}"', f'"{new}"')
                    else:
                        text = text.replace(f"'{old}'", f"'{new}'")
            if text != original:
                path.write_text(text, encoding="utf-8")
                changes += 1
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--roots", nargs="+", default=["lca", "lca_kernel"])
    parser.add_argument("--max", type=int, default=5)
    args = parser.parse_args()

    plan = _load_plan()
    moves = _collect_moves(args.max, args.roots, plan)
    print(f"Planned moves: {len(moves)}")
    for src, dst in moves[:40]:
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
    if len(moves) > 40:
        print(f"  ... and {len(moves) - 40} more")

    if not args.apply:
        print("\nDRY-RUN — re-run with --apply")
        return 0

    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not (dst.parent / "__init__.py").exists():
            (dst.parent / "__init__.py").write_text('"""Auto-created by split_oversized_directories."""\n', encoding="utf-8")
        subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT, check=True)

    n = _rewrite_imports(moves)
    print(f"\nAPPLIED {len(moves)} moves; updated imports in {n} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
