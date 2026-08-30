"""CI gate: enforce plugin metadata completeness.

A plugin must declare all 4 elements:
  1. Identity   — id, layer, kind (already required)
  2. Capability — provides, requires (already required)
  3. Interaction — logic_address (functional_group, control_slot, scope,
                     authority, evidence, revision) + relations + ownership
  4. Verification — test_suite, properties, fixtures

Currently this gate covers element #3 (interaction). Element #4 is covered
by tests/test_*.py file existence (separate concern).

Exempt: legacy plugins listed in legacy_blacklist.txt (PR-4 backlog).

Usage:
  python scripts/check_plugin_metadata.py [--root PATH] [--json]
Exit code: 1 if any plugin missing required metadata.

Refs: docs/superpowers/specs/2026-08-30-comprehensive-cleanup-execution.md §3.4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Phase D (PR-4) gate:
#   logic_address missing → critical
#   ownership / relations / test_suite missing → warning
# Phase E (after PR-4 completes): all four → critical.
ELEMENT_LEVEL = {
    "logic_address": "critical",
    "ownership": "critical",
    "relations": "warning",
    "test_suite": "warning",
}


def main(argv: list[str] | None = None) -> int:
    # Delegate to codegen for the actual AST work.
    from codegen_plugin_metadata import scan  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca" / "plugins")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plugins = scan(args.root)
    critical = [p for p in plugins if p.gap_severity == "critical"]
    warning = [p for p in plugins if p.gap_severity == "warning"]

    if args.json:
        import json
        print(json.dumps({
            "total": len(plugins),
            "critical": len(critical),
            "warning": len(warning),
            "critical_plugins": [
                {"id": p.plugin_id, "file": p.file, "line": p.line}
                for p in critical
            ],
        }, indent=2))
        return 1 if critical else 0

    if not critical and not warning:
        print(f"plugin-metadata: all {len(plugins)} plugins have 4 elements declared.")
        return 0

    print(f"plugin-metadata: {len(plugins)} scanned, "
          f"{len(critical)} critical (missing logic_address/ownership), "
          f"{len(warning)} warning (missing relations/test_suite)",
          file=sys.stderr)
    if critical:
        print("\nCRITICAL plugins (logic_address or ownership missing):", file=sys.stderr)
        for p in critical[:20]:
            print(f"  {p.plugin_id:<48} {p.file}:{p.line}", file=sys.stderr)
        if len(critical) > 20:
            print(f"  ... and {len(critical) - 20} more", file=sys.stderr)

    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())