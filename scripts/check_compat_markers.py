#!/usr/bin/env python3
"""Report COMPAT shim markers without delete-when (ADR-0194/0195 P5-06)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"#\s*COMPAT\(")


def main() -> int:
    missing_delete_when: list[str] = []
    total = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md"}:
            continue
        if "vendor" in path.parts or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not PAT.search(text):
            continue
        total += 1
        if "delete_when:" not in text and "delete-when:" not in text:
            missing_delete_when.append(str(path.relative_to(ROOT)))
    print(f"COMPAT markers scanned: {total}")
    if missing_delete_when:
        print("Missing delete-when/delete_when:")
        for p in sorted(missing_delete_when)[:50]:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
