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
        "events/publishers/spine_reflector_assistant",
        "events/publishers/spine_reflector_body_llm",
        "events/publishers/spine_reflector_boot",
        "events/publishers/spine_reflector_cognition",
        "events/publishers/spine_reflector_composio",
        "events/publishers/spine_reflector_control",
        "events/publishers/spine_reflector_kernel_loop",
        "events/publishers/spine_reflector_perception",
        "events/publishers/spine_reflector_phase",
        "events/publishers/spine_reflector_phase_graph",
        "events/publishers/spine_reflector_runtime",
        "events/publishers/spine_reflector_skill",
        "events/publishers/spine_reflector_team",
        "events/publishers/spine_reflector_transport",
        "events/publishers/spine_reflector_writable",
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

    # Warn-only: count legacy reflector dirs still present
    reflector_parent = PLUGINS / "events" / "publishers"
    if reflector_parent.is_dir():
        reflectors = [
            d.name
            for d in reflector_parent.iterdir()
            if d.is_dir() and d.name.startswith("spine_reflector")
        ]
        if len(reflectors) > 0:
            errs.append(
                f"DEBT: {len(reflectors)} spine_reflector plugin dirs remain "
                f"(target: delete in ADR-0195 P2): {sorted(reflectors)[:5]}..."
            )

    return errs


def main() -> int:
    errs = _errors()
    if not errs:
        print("check_platform_directory: OK")
        return 0
    print("check_platform_directory: FAIL", file=sys.stderr)
    for e in errs:
        print(f"  - {e}", file=sys.stderr)
    # DEBT lines are informational in P0 — still exit 0 if only DEBT
    hard = [e for e in errs if not e.startswith("DEBT:")]
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
