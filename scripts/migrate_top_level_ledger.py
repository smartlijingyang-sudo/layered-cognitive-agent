#!/usr/bin/env python3
"""ADR-0096 P2-4: Archive the legacy top-level journal to v1.archive.

The legacy ``traces/lca_journal.jsonl`` accumulated journal.v1 entries
between deployments; per-run ``traces/runs/<id>/journal.jsonl`` is now
the canonical source (lca.journal/2 envelope + ULID event_id, since
MVA-1 + MVA-2).

This script:
1. Renames ``traces/lca_journal.jsonl`` → ``traces/lca_journal.v1.archive.jsonl``
2. Writes a one-line stub at ``traces/lca_journal.jsonl`` documenting the
   migration (the file is no longer actively written)
3. Is idempotent and refuses to overwrite an existing archive.

Run from repo root. Reversible: ``mv traces/lca_journal.v1.archive.jsonl traces/lca_journal.jsonl``
to un-archive.

Data loss note (2026-08-28):
The first version of this script used ``OLD_PATH.rename(ARCHIVE_PATH)`` which
silently overwrote an existing archive on POSIX (rename(2) is atomic but
unconditional). On first run with a pre-existing 9.7 MB / 26856-line archive,
that archive was clobbered with a 1-line migration marker. The fixed version
explicitly checks for an existing archive and refuses to overwrite unless
the source is clearly the migration stub. Future invocations are safe.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OLD_PATH = REPO_ROOT / "traces" / "lca_journal.jsonl"
ARCHIVE_PATH = REPO_ROOT / "traces" / "lca_journal.v1.archive.jsonl"

MIGRATION_STUB = (
    '{"_migration_marker": "v1.0.0 -> v2.0.0 archived at 2026-08-28", '
    '"see": "traces/lca_journal.v1.archive.jsonl", '
    '"canonical_source": "traces/runs/<run_id>/journal.jsonl (per-run v2 envelopes)"}'
)


def main() -> int:
    if not OLD_PATH.exists() and not ARCHIVE_PATH.exists():
        print(f"FAIL: neither {OLD_PATH} nor {ARCHIVE_PATH} exists.")
        print("       Has the top-level journal already been migrated or never created?")
        return 1

    # Idempotent: if archive already exists, don't overwrite it.
    if ARCHIVE_PATH.exists():
        # Both exist → check if OLD_PATH is the migration stub (small file with marker)
        if OLD_PATH.exists():
            old_content = OLD_PATH.read_text(encoding="utf-8").strip()
            if "_migration_marker" in old_content:
                # Already migrated: archive has real data, OLD_PATH has stub.
                print(f"OK: already migrated. Archive at {ARCHIVE_PATH}")
                print(f"    Stub at {OLD_PATH}")
                return 0
            # OLD_PATH has real data and ARCHIVE also exists → conflict.
            print(f"FAIL: both {OLD_PATH.name} and {ARCHIVE_PATH.name} exist with real content.")
            print(f"  {OLD_PATH.name} size: {OLD_PATH.stat().st_size}")
            print(f"  {ARCHIVE_PATH.name} size: {ARCHIVE_PATH.stat().st_size}")
            print("       Resolve manually to avoid data loss.")
            return 2
        # ARCHIVE exists, OLD_PATH missing → already fully migrated.
        print(f"OK: already migrated. Archive at {ARCHIVE_PATH}")
        return 0

    if OLD_PATH.exists():
        line_count = sum(1 for _ in OLD_PATH.open())
        # SAFE rename: refuse if target exists.
        # Use os.replace with explicit overwrite protection:
        import os

        try:
            os.replace(OLD_PATH, ARCHIVE_PATH)  # atomic on POSIX; overwrites if target exists
            print(f"Archived {line_count} v1 entries: {OLD_PATH.name} -> {ARCHIVE_PATH.name}")
        except OSError as exc:
            print(f"FAIL: rename failed: {exc}")
            print("  This is intentional to prevent data loss.")
            return 3
        OLD_PATH.write_text(MIGRATION_STUB + "\n", encoding="utf-8")
        print(f"Wrote migration stub to {OLD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
