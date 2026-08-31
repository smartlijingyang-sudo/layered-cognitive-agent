"""Migrate lca.layer0/1/2/3/4 → semantic names. One-shot, no shim.

Usage:
    uv run python scripts/migrate_layer_rename.py --dry-run
    uv run python scripts/migrate_layer_rename.py --execute
    uv run python scripts/migrate_layer_rename.py --only layer0
    uv run python scripts/migrate_layer_rename.py --rollback <commit_sha>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

LAYER_TO_SEMANTIC: dict[str, str] = {
    "lca.infrastructure": "lca.infrastructure",
    "lca.cognition": "lca.cognition",
    "lca.runtime": "lca.runtime",
    "lca.agent": "lca.agent",
    "lca.application": "lca.application",
}


@dataclass
class Change:
    path: str
    kind: str  # "git_mv" | "edit"


def list_all_python_md_yaml() -> list[str]:
    """List files that may contain imports or paths."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    all_files = set(result.stdout.split("\0")) | set(tracked.stdout.split("\0"))
    all_files.discard("")
    relevant = [
        f
        for f in all_files
        if f.endswith((".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".json"))
        and not f.startswith(("vendor/", "lobehub-ui/", "node_modules/", ".git/"))
        and "__pycache__" not in f
    ]
    return sorted(relevant)


def find_references() -> dict[str, list[tuple[str, str]]]:
    """Find all references to old layer names. Returns {old: [(file, line), ...]}."""
    refs: dict[str, list[tuple[str, str]]] = {}
    for old in LAYER_TO_SEMANTIC:
        refs[old] = []
    for filepath in list_all_python_md_yaml():
        try:
            content = open(filepath, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            for old in LAYER_TO_SEMANTIC:
                if old in line:
                    refs[old].append((filepath, f"L{i}: {line.strip()[:120]}"))
    return refs


def run_git_mv(dry_run: bool, only: list[str] | None = None) -> list[str]:
    """git mv old paths to new paths. Returns list of moves performed."""
    moves = []
    for old, new in LAYER_TO_SEMANTIC.items():
        if only and not any(o in old for o in only):
            continue
        old_path = old.replace(".", "/")
        new_path = new.replace(".", "/")
        if not (Path_for(old_path)).exists():
            print(f"[skip] {old_path} does not exist")
            continue
        cmd = ["git", "mv", old_path, new_path]
        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
        else:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"moved: {old_path} -> {new_path}")
        moves.append(f"{old_path} -> {new_path}")
    return moves


def Path_for(p: str):
    from pathlib import Path

    return Path(p)


def replace_imports(dry_run: bool, only: list[str] | None = None) -> tuple[int, int]:
    """Replace old layer names in all relevant files. Returns (files_changed, total_replacements)."""
    files = list_all_python_md_yaml()
    total_files = 0
    total_replacements = 0
    for filepath in files:
        try:
            content = open(filepath, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        new_content = content
        file_changed = False
        for old, new in LAYER_TO_SEMANTIC.items():
            if only and not any(o in old for o in only):
                continue
            if old in new_content:
                count = new_content.count(old)
                new_content = new_content.replace(old, new)
                total_replacements += count
                file_changed = True
        if file_changed:
            total_files += 1
            if dry_run:
                # Show first 3 lines that changed
                old_lines = set(content.splitlines())
                new_lines = set(new_content.splitlines())
                print(f"[dry-run] edit {filepath}")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"edited: {filepath}")
    return total_files, total_replacements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--only", help="only process layers matching this (e.g. 'layer0' or 'layer')"
    )
    parser.add_argument("--rollback", help="git revert commit SHA")
    parser.add_argument("--report", action="store_true", help="just show reference counts")
    args = parser.parse_args()

    if args.rollback:
        result = subprocess.run(["git", "revert", "-m", "1", args.rollback], check=False)
        return result.returncode

    if args.report:
        refs = find_references()
        total = 0
        for old, items in refs.items():
            new = LAYER_TO_SEMANTIC[old]
            print(f"{old} -> {new}: {len(items)} references")
            total += len(items)
        print(f"TOTAL: {total} references")
        return 0

    if not (args.dry_run or args.execute):
        print("must pass --dry-run, --execute, --report, or --rollback", file=sys.stderr)
        return 2

    only = [args.only] if args.only else None
    print(f"=== {'DRY-RUN' if args.dry_run else 'EXECUTE'} MODE ===")
    print(f"=== Only: {only or 'all layers'} ===")
    print()

    print("Step 1: git mv")
    run_git_mv(dry_run=args.dry_run, only=only)
    print()

    print("Step 2: replace imports in files")
    files_changed, total_replacements = replace_imports(dry_run=args.dry_run, only=only)
    print()
    print(f"=== Summary: {files_changed} files changed, {total_replacements} replacements ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
