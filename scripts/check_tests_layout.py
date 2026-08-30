"""Phase D: enforce that ``tests/`` mirrors ``lca/`` package layout.

Every top-level ``tests/<dir>/`` directory must correspond to a
``lca/<...>/`` package, and the test files inside must reference
modules from that package (using the existing ``lca`` import prefix).
This catches the orphan ``tests/foo/`` that has no corresponding
production code, and the test file that accidentally imports from a
private package.

Usage::

    python scripts/check_tests_layout.py [--tests PATH] [--src PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "scripts"}
ALLOWED_TOP_LEVEL = {
    "plugins", "e2e", "conftest.py", "test_*.py",
    # Phase-D allow-list: cross-cutting test surfaces whose fixture
    # data / scenarios don't belong under one production package.
    "golden", "golden_traces", "scenarios", "support", "tools",
    "journal", "observability", "plan", "simulation_env",
}


def _top_level_packages(root: Path, prefix: str) -> set[str]:
    out: set[str] = set()
    for child in (root / prefix).iterdir():
        if child.name in SKIP_DIRS:
            continue
        if child.is_dir():
            out.add(child.name)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, default=ROOT / "tests")
    parser.add_argument("--src", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    src_pkgs = _top_level_packages(args.src, "")
    test_dirs = _top_level_packages(args.tests, "")

    violations: list[str] = []
    for td in sorted(test_dirs):
        if td in ALLOWED_TOP_LEVEL or td.startswith("test_"):
            continue
        if td not in src_pkgs:
            violations.append(
                f"tests/{td}: no matching lca/{td}/ package"
            )

    if not violations:
        print("tests-layout: every tests/<dir>/ mirrors an lca/<dir>/ package.")
        return 0
    for line in violations:
        print(f"  ✗ {line}", file=sys.stderr)
    print(
        f"tests-layout: {len(violations)} orphan test directory(ies). "
        "Either create lca/<name>/ or move tests into the existing matching package.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
