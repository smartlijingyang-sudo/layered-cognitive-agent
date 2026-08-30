#!/usr/bin/env python3
"""Pre-commit hook: enforce `docs/` layering rules from docs/AGENTS.md.

`docs/` only contains current architecture decisions, specifications, long-lived
architecture designs, observability documentation, and third-party skill bundles.
Plans, research notes, status records, reviews, and reports belong in `history/`.

Usage:
    uv run python scripts/check_doc_layering.py
    uv run python scripts/check_doc_layering.py --strict  # compatibility alias

Exit code 0 if clean, 1 if any violation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Top-level directories allowed under `docs/`.
ALLOWED_TOP_DIRS: frozenset[str] = frozenset(
    {
        "adr",
        "specs",
        "design",
        "observability",
        # Third-party skill bundles (not LCA-authored docs).
        "superpowers",
    }
)

# Files allowed directly under `docs/` (root level).
ALLOWED_TOP_FILES: frozenset[str] = frozenset({"AGENTS.md"})

# Directories whose `.md` files are exempt from suffix checks (constitution-grade
# designs and ADR files may carry domain terms like "run-plan" or "audit").
SUFFIX_EXEMPT_DIRS: frozenset[str] = frozenset({"adr", "design"})

# ADR filename prefix that exempts a file from the suffix check.
ADR_PREFIX = re.compile(r"^\d{4}-")

# Filename suffixes that signal process / status docs — forbidden at any depth.
FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    "-review",
    "-audit",
    "-explained",
    "-plan",
    "-notes",
)

# Filename suffix indicating locale duplicate — forbidden at any depth.
FORBIDDEN_LOCALE_SUFFIX = ".zh-CN.md"


def _is_forbidden_suffix(stem: str) -> str | None:
    for suffix in FORBIDDEN_SUFFIXES:
        if stem.endswith(suffix) or stem.endswith(suffix + ".md"):
            return suffix
    return None


def _iter_md_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*.md") if p.is_file())


def _check(strict: bool) -> list[str]:
    violations: list[str] = []

    if not DOCS.exists():
        return violations

    # 1. Top-level entries
    for entry in sorted(DOCS.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name not in ALLOWED_TOP_DIRS:
                violations.append(f"forbidden top-level directory: docs/{entry.name}/")
        elif entry.is_file() and entry.name not in ALLOWED_TOP_FILES:
            violations.append(
                f"forbidden top-level file: docs/{entry.name} "
                f"(only AGENTS.md is allowed at docs/ root)"
            )

    # 2. Forbidden filename suffixes and locale duplicates anywhere under docs/
    for path in _iter_md_files(DOCS):
        name = path.name
        stem = path.stem  # without .md
        # AGENTS.md is exempt at any depth
        if name == "AGENTS.md":
            continue
        # Locale duplicate (always forbidden, including inside adr/specs/design).
        if name.endswith(FORBIDDEN_LOCALE_SUFFIX):
            violations.append(
                f"locale-duplicate filename: {path.relative_to(ROOT)} "
                f"(use ADR instead of <topic>.zh-CN.md)"
            )
            continue
        # ADR files and design/ documents are exempt from suffix check
        # (legitimate domain terms: "run-plan", "architecture-audit").
        parent_dir = path.parent.name
        if ADR_PREFIX.match(name) or parent_dir in SUFFIX_EXEMPT_DIRS:
            continue
        # Suffix-based forbidden
        bad_suffix = _is_forbidden_suffix(stem)
        if bad_suffix is not None:
            violations.append(
                f"forbidden suffix {bad_suffix!r}: {path.relative_to(ROOT)} "
                f"(process/status docs go to git history, not docs/)"
            )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Compatibility alias; all unsupported docs directories are always errors.",
    )
    args = parser.parse_args()
    violations = _check(strict=args.strict)
    if not violations:
        print("OK: docs/ layering clean.")
        return 0
    print(f"FAIL: {len(violations)} docs/ layering violation(s):")
    for v in violations:
        print(f"  - {v}")
    print(
        "\nFix per docs/AGENTS.md: move process, research, status, review, and "
        "report records to history/; keep docs/ for current decisions and specifications."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
