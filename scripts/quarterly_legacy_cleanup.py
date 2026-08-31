"""Quarterly cleanup for legacy_blacklist.txt.

Scans each entry in legacy_blacklist.txt and reports:
- Stable: no PRs in last 90 days (candidate for actual rename to remove from list)
- Active: recent PRs (still being modified; keep in legacy)

Usage:
    uv run python scripts/quarterly_legacy_cleanup.py [--dry-run] [--days 90]
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "legacy_blacklist.txt"

DEFAULT_DAYS = 90


@dataclass
class Entry:
    path: str
    note: str
    last_touched: str | None  # git short SHA or date
    days_since: int | None

    @property
    def is_stable(self) -> bool:
        return self.days_since is not None and self.days_since > DEFAULT_DAYS


def parse_legacy() -> list[Entry]:
    if not LEGACY.exists():
        return []
    entries: list[Entry] = []
    for line in LEGACY.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)
        if len(line) == 2:
            path, note = line[0].strip(), "#" + line[1]
        else:
            path, note = line[0].strip(), ""
        if not path or path.startswith("#"):
            continue
        entries.append(Entry(path=path, note=note.strip(), last_touched=None, days_since=None))
    return entries


def get_last_touch(path: str) -> str | None:
    """Get the last commit SHA that touched this path."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%h %ai", "-n", "1", "--", path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    line = result.stdout.strip().splitlines()
    if not line:
        return None
    return line[0]


def days_since_commit(commit_info: str) -> int | None:
    """Parse 'short_sha YYYY-MM-DD HH:MM:SS TZ' and return days since."""
    parts = commit_info.split(maxsplit=2)
    if len(parts) < 2:
        return None
    try:
        date_str = parts[1]
        commit_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    now = datetime.now()
    return (now - commit_date).days


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="stable threshold")
    args = parser.parse_args()

    entries = parse_legacy()
    print(f"Scanning {len(entries)} legacy entries (stable threshold: {args.days} days)")

    stable: list[Entry] = []
    active: list[Entry] = []

    for entry in entries:
        touch = get_last_touch(entry.path)
        if not touch:
            entry.last_touched = "NEVER"
            entry.days_since = None
            stable.append(entry)
            continue
        commit_sha, date_str = touch.split(maxsplit=1)
        entry.last_touched = f"{commit_sha} ({date_str})"
        entry.days_since = days_since_commit(touch)
        if entry.days_since is not None and entry.days_since > args.days:
            stable.append(entry)
        else:
            active.append(entry)

    print(f"\n=== STABLE ({len(stable)} entries, candidate for rename) ===")
    for entry in stable:
        print(
            f"  {entry.path:60s} last: {entry.last_touched}  ({entry.days_since} days)"
            if entry.days_since
            else f"  {entry.path:60s} last: {entry.last_touched}"
        )

    print(f"\n=== ACTIVE ({len(active)} entries, keep in legacy) ===")
    for entry in active:
        print(f"  {entry.path:60s} last: {entry.last_touched}  ({entry.days_since} days)")

    print("\n=== Summary ===")
    print(f"  total: {len(entries)}")
    print(f"  stable: {len(stable)} (rename candidates)")
    print(f"  active: {len(active)} (keep)")

    if args.dry_run:
        print("\n(dry-run mode, no changes made)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
