#!/usr/bin/env python3
"""Verify that documents stay within their word-count budgets.

Usage:
    uv run python scripts/verify_doc_budgets.py

Exit code 0 if all documents are within budget, 1 if any exceed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "scripts" / "doc_budgets.json"


def count_words(text: str) -> int:
    """Count words in text. Chinese characters count as 1 word each."""
    # Split on whitespace for English words
    words = text.split()

    # Count Chinese characters separately (each char = 1 word)
    chinese_chars = sum(1 for word in words for char in word if "\u4e00" <= char <= "\u9fff")

    # English words (non-Chinese)
    english_words = sum(
        1 for word in words if not any("\u4e00" <= char <= "\u9fff" for char in word)
    )

    return english_words + chinese_chars


def main() -> int:
    if not BUDGET_FILE.exists():
        print(f"❌ Budget file not found: {BUDGET_FILE}")
        return 1

    budgets = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    violations: list[tuple[str, int, int]] = []

    for doc_path_str, budget in budgets.items():
        doc_path = ROOT / doc_path_str

        if not doc_path.exists():
            print(f"⚠️  Budget entry for missing file: {doc_path_str}")
            continue

        # Strip code blocks and comments for word count
        # Remove fenced code blocks
        text = Path(doc_path_str).read_text(encoding="utf-8")
        import re

        text = re.sub(r"```[\s\S]*?```", "", text)
        # Remove inline code
        text = re.sub(r"`[^`]+`", "", text)
        # Remove HTML comments
        text = re.sub(r"<!--[\s\S]*?-->", "", text)

        word_count = count_words(text)

        if word_count > budget:
            violations.append((doc_path_str, word_count, budget))

    # Report results
    if violations:
        print(f"❌ {len(violations)} document(s) exceed budget:\n")
        for doc_path, count, budget in violations:
            print(f"  {doc_path}")
            print(f"    current: {count} words")
            print(f"    budget:  {budget} words")
            print(f"    over by: {count - budget} words")
            print()
        print("When the gate goes red:")
        print("  1. Relocate content that belongs in another tier")
        print("  2. Condense content that belongs here but can be shorter")
        print("  3. Raise the ceiling only when the words need the space (justify in PR)")
        return 1

    print(f"✅ All {len(budgets)} documents within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
