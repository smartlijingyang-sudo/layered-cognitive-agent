#!/usr/bin/env python3
"""Move flat tests/test_*.py into tests/scenario/<bucket>/ (≤5 files per bucket).

Buckets by second token: test_run_foo.py -> scenario/run/test_run_foo.py

Usage:
    uv run python scripts/organize_tests_root.py --dry-run
    uv run python scripts/organize_tests_root.py --apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
MAX_PER_DIR = 5


def _bucket(name: str) -> str:
    # test_run_foo_bar -> run
    m = re.match(r"test_([a-z0-9]+)", name)
    return m.group(1) if m else "misc"


def _plan_moves() -> list[tuple[Path, Path]]:
    files = sorted(TESTS.glob("test_*.py"))
    buckets: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        buckets[_bucket(f.name)].append(f)

    moves: list[tuple[Path, Path]] = []
    for bucket, group in sorted(buckets.items()):
        for i, src in enumerate(group):
            sub = bucket if len(group) <= MAX_PER_DIR else f"{bucket}_{i // MAX_PER_DIR}"
            dst_dir = TESTS / "scenario" / sub
            dst = dst_dir / src.name
            moves.append((src, dst))
    return moves


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    moves = _plan_moves()
    print(f"planned moves: {len(moves)}")
    for src, dst in moves[:20]:
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
    if len(moves) > 20:
        print(f"  ... and {len(moves) - 20} more")

    if not args.apply:
        print("\nDRY-RUN — re-run with --apply")
        return 0

    for src, dst in moves:
        if not src.exists():
            continue
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT, check=True)
        init = dst.parent / "__init__.py"
        if not init.exists():
            init.write_text("")

    print(f"\nAPPLIED {len(moves)} test moves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
