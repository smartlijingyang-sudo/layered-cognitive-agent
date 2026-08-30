"""Phase D: validate package directory names are domain nouns.

Per naming-constitution §1, every package path component must be a
single noun (lowercase, optional underscores, no hyphens, no abstract
suffixes like ``_utils`` / ``_helpers`` / ``_stuff``). Module names
under a package follow the same rule inside their filename.

This check inspects every directory under ``lca/`` (and recursively)
and flags the bare nouns that:
  - contain trailing underscore (e.g. ``foo_``)
  - are singular abstract ("misc", "common", "shared") without an
    explicit allow-list
  - contain hyphens (should be underscores)

Usage::

    python scripts/check_package_noun.py [--root PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "traces"}

ALLOWED_ABSTRACT = {"common"}  # domain-specific exemption list
ABSTRACT_REJECTED = {"misc", "shared", "stuff", "tmp", "test", "tests"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    violations: list[str] = []
    for directory in sorted(args.root.rglob("*")):
        if not directory.is_dir():
            continue
        if any(part in SKIP_DIRS for part in directory.parts):
            continue
        name = directory.name
        rel = directory.relative_to(args.root.parent).as_posix()
        if not NAME_RE.match(name):
            violations.append(f"{rel}: invalid Python name {name!r}")
            continue
        if name.endswith("_") and name != name.rstrip("_"):
            violations.append(f"{rel}: trailing underscore")
        if name in ABSTRACT_REJECTED:
            violations.append(f"{rel}: rejected abstract name {name!r}")

    if not violations:
        print("package-noun: every directory name is a domain noun.")
        return 0
    for line in violations:
        print(f"  ✗ {line}", file=sys.stderr)
    print(
        f"package-noun: {len(violations)} violations. "
        "Use a domain noun phrase (lowercase + underscores).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
