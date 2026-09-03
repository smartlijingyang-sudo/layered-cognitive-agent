#!/usr/bin/env python3
"""Read-only lint for stale-time / change-log prose in ``docs/``.

Slop-patterns — words and phrases that signal the document is describing
how things **used to be** rather than the current state — are flagged
when they appear in current-state prose. The goal is to keep ``docs/``
honest: a reader should never have to read a sentence like "previously,
Foo did X; now Bar does X" to understand the system as it is.

What this script does:

1. Walks every ``*.md`` under ``docs/`` by default, **excluding**
   ``docs/adr/`` (free-form historical record), ``docs/notes/`` (also
   free-form), ``docs/debug/`` (the SOP is explicitly historical analysis),
   ``docs/agent_loop_industry_review.md`` (review), and ``docs/design/``
   files dated ``2026-*`` (historical design notes are allowed to use
   past tense to talk about the journey).
2. Strips fenced code blocks, indented code blocks, and HTML comments
   so we don't flag legitimate code samples.
3. Greps the remaining prose for the patterns listed below. A match
   produces a finding keyed by file → pattern → line content.

Patterns (English + Chinese; ``退役`` only flagged in current-state
prose, not in postmortems — postmortems are excluded from scan scope
already because ``docs/design/2026-*`` is the design-deck archive):

- ``\\bpreviously\\b``
- ``\\bused to\\b``
- ``\\bno longer\\b``
- ``\\bnow\\b`` (when used in contrastive prose)
- ``\\bthis PR\\b``
- ``\\bcommit [0-9a-f]{7}\\b`` (bare 7-char hash in prose)
- ``\\bdecision \\d+\\b``
- ``\\b§N of`` (cross-document section references in current-state docs)
- ``the old ``
- ``the previous ``
- ``在 PR #\\d+``
- ``曾经``
- ``退役`` (current-state only; postmortems are excluded)

Output is a markdown table (or ``--json`` for CI). Exit 0 if empty, 1 if
findings, 2 on fatal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"

# Paths excluded from the scan entirely. These are intentionally
# historical / free-form / SOP-oriented — flagging slop in them would
# defeat the purpose.
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "adr",       # ADR free-form historical record
        "notes",     # Agent Notes free-form
        "debug",     # SOP / debug cookbook
        "superpowers",  # third-party skill bundles
    }
)
_EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "agent_loop_industry_review.md",
    }
)

# Patterns we flag in current-state prose. Each entry is (regex, label).
# Order matters only for stable JSON output.
_SLOP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpreviously\b"), "previously"),
    (re.compile(r"\bused to\b"), "used-to"),
    (re.compile(r"\bno longer\b"), "no-longer"),
    (re.compile(r"\bthis PR\b"), "this-pr"),
    (re.compile(r"\bcommit [0-9a-f]{7}\b"), "bare-commit-hash"),
    (re.compile(r"\bdecision \d+\b"), "decision-N"),
    (re.compile(r"\b§N of"), "section-ref-of"),
    (re.compile(r"the old "), "the-old"),
    (re.compile(r"the previous "), "the-previous"),
    (re.compile(r"在 PR #\d+"), "zh-pr-N"),
    (re.compile(r"曾经"), "zh-once"),
    (re.compile(r"退役"), "zh-retire"),
]

# ``\bnow\b`` is contextual — only flag when it appears to contrast
# with a previous state. We approximate by checking that the same
# sentence also contains a "past" marker (``previously`` / ``used to``
# / ``earlier`` / ``before``) OR that ``now`` is followed by an
# em-dash / comma introducing a contrast. This is heuristic; false
# positives are acceptable (better to ask a human to rephrase than to
# ship silent staleness).
_NOW_RE = re.compile(r"\bnow\b")
_NOW_CONTEXT_RE = re.compile(
    r"\b(now|then|earlier|before|previously|before this)\b", re.IGNORECASE
)
_NOW_CONTRAST_TAIL_RE = re.compile(r"\bnow\b[^.]*[,—–-]\s*(?:this|the |today|instead|rather)")


@dataclass
class SlopHit:
    path: str
    pattern: str
    line_no: int
    line: str


# ── file walking & stripping ──────────────────────────────────────


def _iter_md_files(base: Path) -> list[Path]:
    """Walk ``docs/`` and return every ``*.md`` not in the exclusion set."""
    out: list[Path] = []
    for path in sorted(base.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        first = rel.parts[0] if rel.parts else ""
        if first in _EXCLUDED_DIRS:
            continue
        if path.name in _EXCLUDED_FILES:
            continue
        # Exclude dated design docs (docs/design/2026-*.md) — these are
        # historical analysis and are allowed to use past tense.
        if first == "design" and re.match(r"^\d{4}-", path.name):
            continue
        out.append(path)
    return out


_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INDENTED_CODE_RE = re.compile(r"(?m)^(?:    |\t).+$")
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_HEADING_RE = re.compile(r"(?m)^#{1,6}\s.*$")
# Quoted examples: lines starting with ``> `` — blockquote prefix.
# We strip them entirely so the same prose shows up only once.
_BLOCKQUOTE_RE = re.compile(r"(?m)^>.*$")


def _strip_for_prose(text: str) -> str:
    """Remove code blocks, comments, and blockquotes so the linter only sees
    current-state narrative sentences."""
    text = _FENCED_CODE_RE.sub("", text)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _INDENTED_CODE_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    return text


# ── per-file scan ─────────────────────────────────────────────────


def _scan_file(path: Path) -> list[SlopHit]:
    hits: list[SlopHit] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hits
    prose = _strip_for_prose(raw)
    rel = str(path.relative_to(_ROOT))
    # Walk per-line on the stripped prose so line numbers are stable
    # within the file.
    for lineno, line in enumerate(prose.splitlines(), start=1):
        # Skip heading lines.
        if _HEADING_RE.match(line):
            continue
        for pattern, label in _SLOP_PATTERNS:
            if pattern.search(line):
                hits.append(SlopHit(
                    path=rel, pattern=label,
                    line_no=lineno, line=line.strip(),
                ))
        # ``\bnow\b`` only flagged when it reads as contrastive.
        if _NOW_RE.search(line) and (
            _NOW_CONTEXT_RE.search(line)
            or _NOW_CONTRAST_TAIL_RE.search(line)
        ):
            hits.append(SlopHit(
                path=rel, pattern="now-contrast",
                line_no=lineno, line=line.strip(),
            ))
    return hits


# ── reporting ─────────────────────────────────────────────────────


def _render_markdown(hits: list[SlopHit]) -> str:
    out: list[str] = []
    out.append("# Doc Slop Check\n\n")
    out.append("Generated by `scripts/verify_doc_slop.py`. Read-only.\n\n")
    out.append("**Scope**: `docs/**/*.md` minus `docs/adr/`, `docs/notes/`,\n")
    out.append("`docs/debug/`, `docs/superpowers/`, `docs/design/2026-*`,\n")
    out.append("and `docs/agent_loop_industry_review.md`. Code blocks,\n")
    out.append("HTML comments, blockquote examples, and headings are\n")
    out.append("stripped before scanning.\n\n")

    if not hits:
        out.append("No slop patterns detected.\n")
        return "".join(out)

    out.append(f"## Hits ({len(hits)})\n\n")
    out.append("| File | Pattern | Line | Matched text |\n")
    out.append("|---|---|---|---|\n")
    # Sort: file → pattern → line for stable output.
    for hit in sorted(hits, key=lambda h: (h.path, h.pattern, h.line_no)):
        text = hit.line.replace("|", "\\|")
        if len(text) > 160:
            text = text[:157] + "…"
        out.append(
            f"| `{hit.path}` | `{hit.pattern}` | {hit.line_no} | {text} |\n"
        )
    out.append("\n")
    out.append("Each hit suggests the prose is describing a change from a\n")
    out.append("previous state rather than the current truth. Rewrite in\n")
    out.append("present tense, or relocate the historical narrative to\n")
    out.append("`docs/design/`, `history/`, or the relevant ADR.\n")
    return "".join(out)


def _render_json(hits: list[SlopHit]) -> str:
    payload = {
        "script": "verify_doc_slop.py",
        "hits": [
            {
                "path": h.path,
                "pattern": h.pattern,
                "line": h.line_no,
                "text": h.line,
            }
            for h in hits
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# ── main ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=_DOCS,
        help="docs tree to scan (default: docs)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit JSON instead of a markdown table (for CI)",
    )
    args = parser.parse_args(argv)

    try:
        md_files = _iter_md_files(args.root)
    except Exception as exc:  # pragma: no cover — defensive only
        print(f"fatal: {exc}", file=sys.stderr)
        return 2

    hits: list[SlopHit] = []
    for path in md_files:
        hits.extend(_scan_file(path))

    if args.as_json:
        sys.stdout.write(_render_json(hits))
    else:
        sys.stdout.write(_render_markdown(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
