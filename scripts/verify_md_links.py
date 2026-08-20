#!/usr/bin/env python3
"""Verify that relative Markdown links resolve — target file exists AND
#fragment points to a real heading slug.

Usage:
    uv run python scripts/verify_md_links.py

Exit code 0 if all links resolve, 1 if any are broken.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

# Patterns to scan for Markdown files
PATTERNS = [
    "docs/**/*.md",
    "AGENTS.md",
    "README.md",
]

# Regex to match Markdown links: [text](url) or [text](url#fragment)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Regex to extract heading anchors from Markdown
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def slugify_heading(heading: str) -> str:
    """Convert a heading to a GitHub-style anchor slug."""
    # Remove leading/trailing whitespace
    slug = heading.strip().lower()
    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", slug)
    # Remove characters that aren't alphanumeric, hyphens, or underscores
    slug = re.sub(r"[^\w\-]", "", slug)
    return slug


def extract_headings(md_path: Path) -> set[str]:
    """Extract all heading anchors from a Markdown file."""
    if not md_path.exists():
        return set()

    content = md_path.read_text(encoding="utf-8")
    headings = set()

    for match in HEADING_RE.finditer(content):
        heading_text = match.group(2)
        slug = slugify_heading(heading_text)
        headings.add(slug)

    return headings


def verify_link(source_file: Path, link: str) -> tuple[bool, str]:
    """Verify a single link resolves. Returns (ok, error_message)."""
    # Skip absolute URLs and anchors
    if link.startswith(("http://", "https://", "mailto:", "#")):
        return True, ""

    # Split URL and fragment
    if "#" in link:
        url_part, fragment = link.split("#", 1)
    else:
        url_part = link
        fragment = None

    # Resolve target path
    target_path = (source_file.parent / url_part).resolve() if url_part else source_file

    # Check if target exists
    if not target_path.exists():
        return False, f"target not found: {target_path.relative_to(ROOT)}"

    # Check fragment if present
    if fragment and target_path.suffix == ".md":
        headings = extract_headings(target_path)
        if fragment not in headings:
            return False, f"anchor not found: #{fragment} in {target_path.relative_to(ROOT)}"

    return True, ""


def main() -> int:
    violations: list[tuple[Path, int, str, str]] = []

    # Collect all Markdown files
    md_files: set[Path] = set()
    for pattern in PATTERNS:
        md_files.update(ROOT.glob(pattern))

    # Verify each file
    for md_file in sorted(md_files):
        if not md_file.exists():
            continue

        content = md_file.read_text(encoding="utf-8")

        # Remove code blocks to avoid false positives
        # Remove fenced code blocks (``` ... ```)
        content_no_code = re.sub(r"```[\s\S]*?```", "", content)
        # Remove inline code (` ... `)
        content_no_code = re.sub(r"`[^`]+`", "", content_no_code)

        lines = content_no_code.split("\n")

        for line_num, line in enumerate(lines, start=1):
            for match in LINK_RE.finditer(line):
                link = match.group(2)
                # Skip links that look like code (contain commas, asterisks, etc.)
                if re.search(r"[,*]", link):
                    continue
                ok, error = verify_link(md_file, link)
                if not ok:
                    violations.append((md_file, line_num, link, error))

    # Report results
    if violations:
        print(f"❌ Found {len(violations)} broken link(s):\n")
        for md_file, line_num, link, error in violations:
            rel_path = md_file.relative_to(ROOT)
            print(f"  {rel_path}:{line_num}")
            print(f"    link: {link}")
            print(f"    error: {error}")
            print()
        return 1

    print(f"✅ All links in {len(md_files)} files resolve correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
