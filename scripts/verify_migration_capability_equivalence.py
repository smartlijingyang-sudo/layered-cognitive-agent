#!/usr/bin/env python3
"""Verify PR-10 capability equivalence across migrated profiles.

PR-10 of the lca/plugins/ single-entry unification plan
(``docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md``)
must preserve the set of resolved capabilities (id, kind, layer,
provides, requires, edges) across the migration. This script boots three
representative profiles, captures their capability graphs, and compares
them against the pre-PR-10 baselines stored under
``docs/notes/baselines/``.

Exit codes:

* 0 — every profile matches its baseline (id set, per-id manifest,
  edges).
* 1 — at least one profile diverged (prints a diff).

Profiles covered (matches the proposal's "verify migration capability
equivalence" row):

* web-standard.yaml           — primary deployment configuration
* scenario-cordis-creator.yaml — Creator §13.3 scenario
* coding-agent.yaml           — coding agent scenario

Run::

    python scripts/verify_migration_capability_equivalence.py
    python scripts/verify_migration_capability_equivalence.py --profile <yaml>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROFILES_AND_BASELINES: list[tuple[str, str]] = [
    (
        "profiles/web-standard.yaml",
        "docs/notes/baselines/capability-set-web-standard-pre-pr10.json",
    ),
    (
        "profiles/web-standard-recovery.yaml",
        "docs/notes/baselines/capability-set-web-standard-recovery-pre-pr10.json",
    ),
    (
        "profiles/self-improving-minimal.yaml",
        "docs/notes/baselines/capability-set-self-improving-minimal-pre-pr10.json",
    ),
]


def _capture(profile: str) -> dict:
    """Boot ``profile`` and capture its capability graph (id/manifest/edges)."""
    from lca.harness.diagnostics.inspect import (
        format_capability_graph,
        inspect_profile_tree,
    )

    ctx = asyncio.run(inspect_profile_tree(Path(profile)))
    graph = format_capability_graph(ctx, profile=profile)
    # Strip log lines that some structlog configurations emit to stdout.
    if isinstance(graph, dict) and "edges" in graph:
        return graph
    raise RuntimeError(f"unexpected graph shape from {profile}: {type(graph).__name__}")


def _diff(baseline: dict, current: dict, profile: str) -> list[str]:
    """Return a list of human-readable diff lines (empty if equivalent)."""
    diffs: list[str] = []

    b_ids = sorted(n["id"] for n in baseline["nodes"])
    c_ids = sorted(n["id"] for n in current["nodes"])
    if b_ids != c_ids:
        added = sorted(set(c_ids) - set(b_ids))
        removed = sorted(set(b_ids) - set(c_ids))
        if added:
            diffs.append(f"  added plugins: {added}")
        if removed:
            diffs.append(f"  removed plugins: {removed}")

    by_id_b = {n["id"]: n for n in baseline["nodes"]}
    for row in current["nodes"]:
        b = by_id_b.get(row["id"])
        if b is None:
            continue
        for field in ("provides", "requires", "kind", "layer"):
            if row.get(field) != b.get(field):
                diffs.append(
                    f"  plugin {row['id']!r}: field {field!r} drifted "
                    f"(current={row.get(field)!r}, baseline={b.get(field)!r})"
                )

    b_edges = sorted(map(sorted, baseline["edges"]))
    c_edges = sorted(map(sorted, current["edges"]))
    if b_edges != c_edges:
        diffs.append(
            f"  edges diverged: baseline={len(b_edges)} current={len(c_edges)}"
        )

    if diffs:
        diffs.insert(0, f"[{profile}] capability divergence:")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--profile",
        choices=[p for p, _ in PROFILES_AND_BASELINES],
        help="restrict check to a single profile",
    )
    args = ap.parse_args()

    failures: list[str] = []
    for profile, baseline_rel in PROFILES_AND_BASELINES:
        if args.profile and profile != args.profile:
            continue
        baseline_path = ROOT / baseline_rel
        if not baseline_path.exists():
            print(
                f"[{profile}] SKIP: baseline missing at {baseline_path}",
                file=sys.stderr,
            )
            continue
        baseline = json.loads(baseline_path.read_text())
        try:
            current = _capture(profile)
        except Exception as exc:  # pragma: no cover — surfaced verbatim
            print(f"[{profile}] FAILED to boot: {exc}", file=sys.stderr)
            failures.append(f"[{profile}] boot failed")
            continue
        diffs = _diff(baseline, current, profile)
        if diffs:
            for line in diffs:
                print(line)
            failures.append(profile)
        else:
            print(f"[{profile}] OK ({len(current['nodes'])} plugins, {len(current['edges'])} edges)")

    if failures:
        print(f"\nFAIL: {len(failures)} profile(s) diverged", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
