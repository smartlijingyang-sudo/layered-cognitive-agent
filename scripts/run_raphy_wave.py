#!/usr/bin/env python3
"""scripts/run_raphy_wave.py: Harness to manage Raphy batch waves and story states."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def get_open_stories(prd_path: Path) -> list[dict[str, Any]]:
    """Return all stories that are neither passed nor dropped."""
    if not prd_path.exists():
        return []
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    return [
        s
        for s in data.get("userStories", [])
        if not s.get("passes") and not s.get("dropped")
    ]


def mark_story_pass(prd_path: Path, story_id: str, notes: str = "") -> bool:
    """Mark a story as passed."""
    if not prd_path.exists():
        return False
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    found = False
    for s in data.get("userStories", []):
        if s.get("id") == story_id:
            s["passes"] = True
            if notes:
                s["notes"] = notes
            found = True
            break
    if found:
        prd_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return found


def mark_story_dropped(prd_path: Path, story_id: str, reason: str = "") -> bool:
    """Mark a story as dropped with concrete evidence."""
    if not prd_path.exists():
        return False
    data = json.loads(prd_path.read_text(encoding="utf-8"))
    found = False
    for s in data.get("userStories", []):
        if s.get("id") == story_id:
            s["passes"] = False
            s["dropped"] = True
            existing_notes = s.get("notes", "")
            s["notes"] = f"{existing_notes}\n[DROPPED]: {reason}".strip()
            found = True
            break
    if found:
        prd_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Raphy Wave Runner Harness")
    parser.add_argument(
        "--prd",
        type=Path,
        default=Path("raphy/prd.json"),
        help="Path to prd.json state machine",
    )
    parser.add_argument("--list-open", action="store_true", help="List open stories")
    parser.add_argument("--pass-story", type=str, help="Mark story as passed")
    parser.add_argument("--drop-story", type=str, help="Mark story as dropped")
    parser.add_argument("--notes", type=str, default="", help="Notes/evidence for status")

    args = parser.parse_args()

    if args.pass_story:
        if mark_story_pass(args.prd, args.pass_story, args.notes):
            print(f"Story {args.pass_story} marked as PASSED.")
            return 0
        print(f"Story {args.pass_story} not found.", file=sys.stderr)
        return 1

    if args.drop_story:
        if mark_story_dropped(args.prd, args.drop_story, args.notes):
            print(f"Story {args.drop_story} marked as DROPPED.")
            return 0
        print(f"Story {args.drop_story} not found.", file=sys.stderr)
        return 1

    open_stories = get_open_stories(args.prd)
    print(f"Open stories remaining: {len(open_stories)}")
    for s in open_stories:
        print(f"- [{s.get('id')}] {s.get('title')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
