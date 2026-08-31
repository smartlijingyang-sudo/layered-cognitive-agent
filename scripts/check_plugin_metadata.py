"""CI gate: enforce plugin metadata completeness.

A plugin must declare all 4 elements:
  1. Identity   — id, layer, kind (already required)
  2. Capability — provides, requires (already required)
  3. Interaction — ``contract=PluginContract(...)`` per ADR-0110 D1
                   (canonical 9-section form), or the legacy shorthand
                   ``functional_group=`` / ``logic_address=`` keys
                   (both still tolerated during the 6-month deprecation
                   window per ADR-0110 §one) + relations + ownership
  4. Verification — test_suite, properties, fixtures

Currently this gate covers element #3 (interaction). Element #4 is covered
by tests/test_*.py file existence (separate concern).

Exempt: legacy plugins listed in legacy_blacklist.txt (PR-4 backlog).
Each entry must include a justification comment.

Usage:
  python scripts/check_plugin_metadata.py [--root PATH] [--json]
Exit code: 1 if any plugin missing required metadata (and not in blacklist).

Reference: docs/architecture/plugin-check-matrix.md (the single source of
truth for hard vs soft gate behavior; matches ``lca plugin check`` output).
For full project rationale see ADR-0110 (Plugin Contract Unification and
Naming Convergence, accepted 2026-08-31).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLACKLIST = ROOT / "lca" / "plugins" / "legacy_blacklist.txt"


def load_blacklist() -> set[str]:
    """Load plugin ids from legacy_blacklist.txt.

    Format: one plugin id per line, '#' starts a comment.
    """
    if not BLACKLIST.exists():
        return set()
    ids: set[str] = set()
    for line in BLACKLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.add(line)
    return ids


def main(argv: list[str] | None = None) -> int:
    # Delegate to codegen for the actual AST work.
    from codegen_plugin_metadata import scan  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca" / "plugins")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plugins = scan(args.root)
    blacklist = load_blacklist()
    critical = [p for p in plugins if p.gap_severity == "critical" and p.plugin_id not in blacklist]
    warning = [p for p in plugins if p.gap_severity == "warning" and p.plugin_id not in blacklist]
    exempted = [p for p in plugins if p.plugin_id in blacklist]

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "total": len(plugins),
                    "critical": len(critical),
                    "warning": len(warning),
                    "blacklisted": len(exempted),
                    "critical_plugins": [
                        {"id": p.plugin_id, "file": p.file, "line": p.line} for p in critical
                    ],
                },
                indent=2,
            )
        )
        return 1 if critical else 0

    if not critical and not warning:
        msg = f"plugin-metadata: all {len(plugins)} plugins have 4 elements declared"
        if exempted:
            msg += f" ({len(exempted)} via legacy_blacklist.txt)"
        print(msg + ".")
        return 0

    print(
        f"plugin-metadata: {len(plugins)} scanned, "
        f"{len(critical)} critical (missing contract=PluginContract), "
        f"{len(warning)} warning, "
        f"{len(exempted)} exempted via blacklist",
        file=sys.stderr,
    )
    if critical:
        print("\nCRITICAL plugins (no contract=, not in blacklist):", file=sys.stderr)
        for p in critical[:20]:
            print(f"  {p.plugin_id:<48} {p.file}:{p.line}", file=sys.stderr)
        if len(critical) > 20:
            print(f"  ... and {len(critical) - 20} more", file=sys.stderr)

    if critical or warning:
        # ADR-0110 §八 acceptance item #4: surface the matrix as the single
        # source of truth for what these signals mean.
        print(
            "\nSee docs/architecture/plugin-check-matrix.md for what each "
            "warning / critical means and how to resolve.",
            file=sys.stderr,
        )

    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
