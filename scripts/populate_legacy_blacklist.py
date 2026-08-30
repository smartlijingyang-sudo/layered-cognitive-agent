"""One-shot script to populate legacy_blacklist.txt from current check output.

Usage:
    uv run python scripts/check_filename_boundaries.py 2>&1 | uv run python scripts/populate_legacy_blacklist.py
"""
import re
import sys
from pathlib import Path

LEGACY = Path("legacy_blacklist.txt")

new_entries: list[str] = []
for line in sys.stdin:
    m = re.match(r"^(ERROR|WARN): (\S+):", line)
    if m:
        path = m.group(2)
        new_entries.append(f"{path}  # historical filename; tracked for quarterly cleanup")

if not new_entries:
    print("No entries to add")
    sys.exit(0)

# Read existing entries
existing = set()
if LEGACY.exists():
    for line in LEGACY.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("#"):
            existing.add(line)

added = []
for entry in new_entries:
    path = entry.split("  #")[0].strip()
    if path not in existing:
        added.append(entry)
        existing.add(path)

if not added:
    print(f"All {len(new_entries)} entries already in legacy_blacklist.txt")
    sys.exit(0)

# Append
with open(LEGACY, "a") as f:
    f.write("\n# Auto-populated by check_filename_boundaries.py (Phase 3 Task 2)\n")
    for entry in added:
        f.write(entry + "\n")

print(f"Added {len(added)} entries to legacy_blacklist.txt")
