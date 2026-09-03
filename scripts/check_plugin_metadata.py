r"""CI gate: enforce plugin metadata completeness and id grammar.

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

PR-11 adds ``plugin_id_grammar`` dimension: new plugins under
``lca/plugins/`` MUST use a dot-separated id matching
``^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$``. The baseline at
``docs/notes/baselines/plugin-id-grammar.json`` whitelists every
pre-existing id (legacy ``lca-*`` ids plus already-shipped non-legacy
ids); only ids absent from the baseline trigger the failure. The legacy
``lca-*`` ids are tracked for gradual migration per
``docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md``
PR-11 and shrink toward zero as follow-up rename PRs land.

Usage:
  python scripts/check_plugin_metadata.py [--root PATH] [--json]
Exit code: 1 if any plugin missing required metadata (and not in blacklist),
or any new plugin id violates the grammar rule above.

Reference: docs/architecture/plugin-check-matrix.md (the single source of
truth for hard vs soft gate behavior; matches ``lca plugin check`` output).
For full project rationale see ADR-0110 (Plugin Contract Unification and
Naming Convergence, accepted 2026-08-31).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLACKLIST = ROOT / "lca" / "plugins" / "legacy_blacklist.txt"
GRAMMAR_BASELINE = ROOT / "docs" / "notes" / "baselines" / "plugin-id-grammar.json"

# PR-11 grammar rule: dot-separated, lowercase, snake-friendly segments.
# Each segment = ``[a-z][a-z0-9_]*`` (starts with a letter, contains
# lowercase letters/digits/underscore). At least two segments required.
GRAMMAR_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
LEGACY_PATTERN = re.compile(r"^lca-[a-z0-9-]+$")


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


@dataclass
class GrammarReport:
    """Summary of the ``plugin_id_grammar`` dimension."""

    total: int = 0
    legacy_lca_dash_ids: list[str] = field(default_factory=list)
    non_legacy_ids: list[str] = field(default_factory=list)
    non_legacy_violations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "legacy_lca_dash_count": len(self.legacy_lca_dash_ids),
            "non_legacy_count": len(self.non_legacy_ids),
            "non_legacy_violations": self.non_legacy_violations,
        }


def load_grammar_baseline() -> tuple[set[str], set[str]]:
    """Load pre-existing id whitelists from the PR-11 grammar baseline.

    Returns ``(legacy_ids, non_legacy_ids)``. Missing baseline yields
    empty sets; the gate then flags every non-legacy plugin as a
    violation, which is the safe state when the baseline is absent.
    """
    if not GRAMMAR_BASELINE.exists():
        return set(), set()
    try:
        data = json.loads(GRAMMAR_BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set(), set()
    legacy = set(data.get("legacy_lca_dash_ids", []))
    non_legacy = set(data.get("non_legacy_ids", []))
    return legacy, non_legacy


def scan_grammar(plugins: list) -> GrammarReport:
    """Classify each plugin's id against the baseline + grammar pattern."""
    _legacy_baseline, non_legacy_baseline = load_grammar_baseline()
    report = GrammarReport(total=len(plugins))
    for p in plugins:
        pid = p.plugin_id
        if not pid:
            continue
        if LEGACY_PATTERN.match(pid):
            report.legacy_lca_dash_ids.append(pid)
            continue
        report.non_legacy_ids.append(pid)
        if pid in non_legacy_baseline:
            continue
        if GRAMMAR_PATTERN.match(pid):
            continue
        report.non_legacy_violations.append(
            {
                "id": pid,
                "file": p.file,
                "line": p.line,
                "detail": (
                    f"id={pid!r} is not 'lca-*' legacy and does not match "
                    "dot-separated pattern ^[a-z][a-z0-9_]*(\\\\.[a-z][a-z0-9_]*)+$"
                ),
            }
        )
    return report


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
    grammar = scan_grammar(plugins)

    if args.json:
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
                    "plugin_id_grammar": grammar.to_dict(),
                },
                indent=2,
            )
        )
        return 1 if critical or grammar.non_legacy_violations else 0

    grammar_summary = (
        f"id-grammar: {len(grammar.legacy_lca_dash_ids)} legacy lca-* + "
        f"{len(grammar.non_legacy_ids)} non-legacy "
        f"({len(grammar.non_legacy_violations)} violations)"
    )

    if not critical and not warning and not grammar.non_legacy_violations:
        msg = (
            f"plugin-metadata: all {len(plugins)} plugins have 4 elements declared; "
            f"{grammar_summary}"
        )
        if exempted:
            msg += f" ({len(exempted)} via legacy_blacklist.txt)"
        print(msg + ".")
        return 0

    print(
        f"plugin-metadata: {len(plugins)} scanned, "
        f"{len(critical)} critical (missing contract=PluginContract), "
        f"{len(warning)} warning, "
        f"{len(exempted)} exempted via blacklist; "
        f"{grammar_summary}",
        file=sys.stderr,
    )

    if critical:
        print("\nCRITICAL plugins (no contract=, not in blacklist):", file=sys.stderr)
        for p in critical[:20]:
            print(f"  {p.plugin_id:<48} {p.file}:{p.line}", file=sys.stderr)
        if len(critical) > 20:
            print(f"  ... and {len(critical) - 20} more", file=sys.stderr)

    if grammar.non_legacy_violations:
        print(
            "\nid-grammar: new (post-baseline) plugins with non-legacy ids that "
            "do not match dot-separated pattern:",
            file=sys.stderr,
        )
        for v in grammar.non_legacy_violations:
            print(
                f"  {v['id']:<48} {v['file']}:{v['line']}  {v['detail']}",
                file=sys.stderr,
            )

    if critical or warning:
        # ADR-0110 §八 acceptance item #4: surface the matrix as the single
        # source of truth for what these signals mean.
        print(
            "\nSee docs/architecture/plugin-check-matrix.md for what each "
            "warning / critical means and how to resolve.",
            file=sys.stderr,
        )

    return 1 if critical or grammar.non_legacy_violations else 0


if __name__ == "__main__":
    sys.exit(main())
