#!/usr/bin/env python3
"""Migrate seams/providers tree to domain-keyed layout (PR-10 evidence).

PR-10 of the lca/plugins/ single-entry unification plan
(``docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md``).

This script is the deterministic mapping table from the OLD
``seams/<area>/<name>.py`` + ``providers/<area>/<name>.py`` layout to the
NEW ``<area>/<name>_seam.py`` + ``<area>/<name>_provider.py`` layout
(domain-keyed directories). It does NOT touch git, importers, or bundle
YAML — those are separate mechanical steps that consume this mapping.

Usage::

    python scripts/migrate_seams_providers_to_domain.py --root . --emit renames.txt

The emitted ``renames.txt`` is the source-of-truth move list used by the
PR-10 migration commit. It is intentionally not deleted after the merge:
the note's "delete-when" for PR-10 is the ``seams/`` and ``providers/``
directories going empty, but the mapping script itself stays as evidence
of how the layout was derived.

Mapping rules (per PR-10 row in the note):

* ``lca/plugins/seams/<area>/<name>.py``       → ``lca/plugins/<area>/<name>_seam.py``
* ``lca/plugins/providers/<area>/<name>.py``   → ``lca/plugins/<area>/<name>_provider.py``

Areas recognised (per PR-10 mapping rule):
``perceive / think / act / memory / collaboration / transport /
observability / state / journal / gate``. Anything outside this set is
mapped via the ``ORPHAN_AREA_MAP`` table (a deliberate deviation logged
in the PR-10 deviation list).

Excluded from migration:
* ``__init__.py`` files at any level — they have no @plugin and the
  parent dirs are removed entirely.
* ``__pycache__/`` directories — not tracked by git.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# PR-10 mapping rule's recognised <area> set.
KNOWN_AREAS = frozenset(
    {
        "perceive",
        "think",
        "act",
        "memory",
        "collaboration",
        "transport",
        "observability",
        "state",
        "journal",
        "gate",
    }
)

# Orphan subdirectories of providers/<area> that exist in HEAD but fall
# outside PR-10's 10-area mapping. Each maps to a domain dir chosen by
# what the helper actually does (event_identity → observability because
# ADR-0096/0097 puts event identity under spine observability; etc.).
# Recorded as a deliberate deviation in the PR-10 commit body.
ORPHAN_AREA_MAP: dict[str, str] = {
    "event_identity": "observability",
    "journal_schema": "journal",
    "openai_stream_encoder": "transport",
    "profile_snapshot": "observability",
    "run_ui_encoder": "transport",
}


def _emit_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Return [(old_path, new_path)] for every plugin-shaped file."""
    moves: list[tuple[Path, Path]] = []
    plugins_root = root / "lca" / "plugins"

    # 1. Standard seams/<area>/<name>.py → <area>/<name>_seam.py.
    for area in sorted(KNOWN_AREAS):
        src_dir = plugins_root / "seams" / area
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.glob("*.py")):
            if src.name == "__init__.py":
                continue
            stem = src.stem
            dst = plugins_root / area / f"{stem}_seam.py"
            moves.append((src, dst))

    # 2. Standard providers/<area>/<name>.py → <area>/<name>_provider.py.
    for area in sorted(KNOWN_AREAS):
        src_dir = plugins_root / "providers" / area
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.glob("*.py")):
            if src.name == "__init__.py":
                continue
            stem = src.stem
            dst = plugins_root / area / f"{stem}_provider.py"
            moves.append((src, dst))

    # 3. Orphan provider subdirectories → mapped domain via ORPHAN_AREA_MAP.
    # We keep the orphan subdir name as a stem prefix to avoid collisions
    # in the destination (e.g. openai_stream_encoder/_encoder.py vs
    # run_ui_encoder/_encoder.py would both land at
    # transport/_encoder_provider.py).
    for orphan_area, target_area in ORPHAN_AREA_MAP.items():
        src_dir = plugins_root / "providers" / orphan_area
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.glob("*.py")):
            if src.name == "__init__.py":
                continue
            stem = src.stem
            # The orphan subdir prefix prevents collisions between
            # sibling helpers from different subdirs (e.g. two
            # `_encoder.py` files).
            dst_stem = f"{orphan_area}_{stem}"
            dst = plugins_root / target_area / f"{dst_stem}_provider.py"
            moves.append((src, dst))

    return moves


# Sub-batches recommended by the note (for reviewable PRs). PR-10 collapses
# these into a single commit because the move is mechanical and the
# regression test covers the whole set, but the order is preserved here
# so future re-runs or backouts follow the original plan.
SUB_BATCH_ORDER: list[str] = [
    # Batch 1: largest, most-coupled domains.
    "act",
    "memory",
    # Batch 2: collaborative + transport surfaces.
    "collaboration",
    "transport",
    # Batch 3: observability (largest), journal, state.
    "observability",
    "journal",
    "state",
    # Batch 4: remaining cognitive + decision domains.
    "think",
    "gate",
    "perceive",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument(
        "--emit",
        default="-",
        help="output file for move list (default: stdout)",
    )
    ap.add_argument(
        "--format",
        choices=("git-mv", "rename"),
        default="git-mv",
        help="emit git-mv commands or plain 'src -> dst' rows",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    moves = _emit_pairs(root)
    if not moves:
        print("no plugin files to migrate", file=sys.stderr)
        return 1

    out_lines: list[str] = []
    for src, dst in moves:
        if args.format == "git-mv":
            out_lines.append(f"git mv {src.relative_to(root)} {dst.relative_to(root)}")
        else:
            out_lines.append(f"{src.relative_to(root)}\t{dst.relative_to(root)}")

    text = "\n".join(out_lines) + "\n"
    if args.emit == "-":
        sys.stdout.write(text)
    else:
        Path(args.emit).write_text(text, encoding="utf-8")
        print(f"wrote {len(moves)} moves to {args.emit}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
