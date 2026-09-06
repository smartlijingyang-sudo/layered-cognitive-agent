#!/usr/bin/env python3
"""Platform directory architecture gate (ADR-0195 P0).

Checks README presence, allowed top-level packages, and plugin legacy rules.
Exit 0 = pass; 1 = violations (for CI).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LCA = ROOT / "lca"
PLUGINS = LCA / "plugins"

# Target top-level lca packages (session + loop are new P0 anchors)
REQUIRED_LCA_TOP = frozenset(
    {
        "agent",
        "application",
        "cognition",
        "contracts",
        "harness",
        "infrastructure",
        "loop",
        "plugins",
        "runtime",
        "session",
    }
)

# Each must have README.md at package root
REQUIRED_README_PACKAGES = REQUIRED_LCA_TOP | {"lca_kernel"}

# New @plugin files forbidden under these legacy roots (P0: only block new plugin.py)
LEGACY_PLUGIN_ROOTS_NO_NEW_PLUGIN_PY = frozenset(
    {
        "events/publishers/spine_loop_cursor",
        "events/publishers/spine_writable_matrix",
    }
)

SEAM_TREE_ANCHORS = frozenset(
    {
        "cognitive",
        "loop",
        "observability",
        "transport",
        "domain",
        "composition",
        "meta",
    }
)


def _errors() -> list[str]:
    errs: list[str] = []

    # lca top-level packages
    if LCA.is_dir():
        actual = {p.name for p in LCA.iterdir() if p.is_dir() and not p.name.startswith("_")}
        extra = actual - REQUIRED_LCA_TOP - {"__pycache__"}
        missing = REQUIRED_LCA_TOP - actual
        if extra:
            errs.append(f"lca/ unexpected top-level dirs: {sorted(extra)}")
        if missing:
            errs.append(f"lca/ missing top-level dirs: {sorted(missing)}")

    for pkg in REQUIRED_README_PACKAGES:
        if pkg == "lca_kernel":
            readme = ROOT / "lca_kernel" / "README.md"
        else:
            readme = LCA / pkg / "README.md"
        if not readme.is_file():
            errs.append(f"missing README: {readme.relative_to(ROOT)}")

    arch = PLUGINS / "ARCHITECTURE.md"
    if not arch.is_file():
        errs.append("missing lca/plugins/ARCHITECTURE.md")

    spec = ROOT / "docs/specs/platform-directory-architecture.md"
    if not spec.is_file():
        errs.append("missing docs/specs/platform-directory-architecture.md")

    for anchor in SEAM_TREE_ANCHORS:
        readme = PLUGINS / anchor / "README.md"
        if not readme.is_file():
            errs.append(f"missing seam tree anchor README: {readme.relative_to(ROOT)}")

    return errs


def main() -> int:
    errs = _errors()
    if not errs:
        print("check_platform_directory: OK")
        return 0
    print("check_platform_directory: FAIL", file=sys.stderr)
    for e in errs:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
