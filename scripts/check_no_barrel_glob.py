"""Phase D: forbid wildcard re-exports in any package __init__.py.

Per naming-constitution §6.1: ``__init__.py`` must export an explicit
sorted ``__all__`` instead of relying on ``from X import *``. Wildcard
imports pull in transitive dependencies, break lazy loading, and silently
expand the public surface of every package that re-uses them.

Usage::

    python scripts/check_no_barrel_glob.py [--root PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WILDCARD_PATTERNS = (
    re.compile(r"^\s*from\s+\S+\s+import\s+\*\s*(?:#.*)?$"),
    re.compile(r"^\s*from\s+\S+\.\S+\s+import\s+\*\s*(?:#.*)?$"),
    re.compile(r"^\s*\*\s*$"),
)


def _scan(path: Path):
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            for pattern in WILDCARD_PATTERNS:
                if pattern.match(line):
                    yield lineno, line.rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    violations: list[tuple[Path, int, str]] = []
    for init in sorted(args.root.rglob("__init__.py")):
        for lineno, text in _scan(init):
            violations.append((init, lineno, text))

    if not violations:
        print("no-barrel-glob: every __init__.py uses explicit __all__.")
        return 0
    for path, lineno, text in violations:
        rel = path.relative_to(args.root.parent)
        print(f"  ✗ {rel}:{lineno}: {text}", file=sys.stderr)
    print(
        f"no-barrel-glob: {len(violations)} wildcard import(s). "
        "Replace with an explicit sorted __all__ in each __init__.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
