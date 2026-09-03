#!/usr/bin/env python3
"""Read-only validator for ``docs/notes/`` per ``docs/notes/README.md``.

Scans the Agent Notes tree and reports structural / format violations. The
script never edits anything — it produces a markdown report (or ``--json``
payload) the agent can act on before any tree mutation.

Rules enforced (per ``docs/notes/README.md`` §2.1 / §2.2 / §3):

1. **Lifecycle root** — direct children of ``docs/notes/`` must be in the
   closed set ``{proposed, implemented, rejected}``; ``archived`` is a
   path-level state, so files under ``archived/`` are out of scope for
   the header / ``Status:`` checks (their bodies follow a sealed format).
2. **Class second level** — direct children of each lifecycle directory
   must be in the closed set ``{contract, primitive, seam, profile,
   runbook, postmortem}``; an extra ``AGENTS.md`` per lifecycle root is
   allowed (it carries that lifecycle's local instructions).
3. **Filename pattern** — every note file matches
   ``^\\d{4}-\\d{2}-\\d{2}-.+\\.md$``. ``INDEX.md`` is forbidden
   anywhere in the tree (centralised indexes are explicitly disallowed).
4. **Header three-line** — top of every note (outside ``archived/``)
   must be ``# Agent Note: <title>`` followed by a blank line and
   ``Status: <proposed|implemented|rejected>``.
5. **Status consistency** — the ``Status:`` value MUST match the
   lifecycle directory the file sits under.
6. **Body skeleton** — every note body must contain ``## Problem``
   (mandatory opener) and ``## Alternatives considered`` (mandatory).
7. **Lifecycle root contents** — only ``AGENTS.md`` and ``CLAUDE.md`` are
   permitted at the lifecycle directory root; everything else must live
   under ``{lifecycle}/{class}/...``.

Exit codes: 0 clean, 1 findings, 2 fatal.

This script is the notes-tree counterpart to ``check_adr_supervision.py``;
it deliberately does not touch ``docs/adr/`` (that is the ADR supervisor's
job).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Lifecycle closed set (top level under ``docs/notes/``). Files under
# ``archived/`` are exempt from header / Status checks because that
# directory uses a sealed format with ``Archived: YYYY-MM-DD``.
_LIFECYCLE_DIRS: frozenset[str] = frozenset(
    {"proposed", "implemented", "rejected"}
)

# Non-Note top-level directories that may live next to the lifecycle dirs.
# Per README §2.1: ``templates/`` holds reusable skeletons (not notes);
# ``archived/`` holds frozen notes (also not a lifecycle to validate here);
# ``plans/`` holds write-up plans (proposals for future work, not notes).
_NON_NOTE_TOP_DIRS: frozenset[str] = frozenset(
    {"templates", "archived", "plans"}
)

# Class closed set (second level under each lifecycle dir). AGENTS.md and
# CLAUDE.md are exception files at the lifecycle root, not classes.
_CLASS_DIRS: frozenset[str] = frozenset(
    {"contract", "primitive", "seam", "profile", "runbook", "postmortem"}
)

# Files allowed directly under a lifecycle directory root.
_LIFECYCLE_ROOT_FILES: frozenset[str] = frozenset({"AGENTS.md", "CLAUDE.md"})

# Files allowed directly at ``docs/notes/`` root. Per README §2.1, an
# audit report named ``audit-YYYY-MM-DD.md`` is also allowed (produced by
# ``scripts/audit_adr_health.py`` / ``lca-audit-notes`` skill).
_NOTES_ROOT_FILES: frozenset[str] = frozenset(
    {"README.md", "AGENTS.md", "CLAUDE.md"}
)
_NOTES_ROOT_FILE_RE = re.compile(r"^audit-\d{4}-\d{2}-\d{2}\.md$")

# Filename pattern: ``YYYY-MM-DD-<topic>.md``.
_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.md$")

# ``Status: <lifecycle>`` line. A trailing `` — <reason>`` is allowed
# (per README §3.1, ``rejected`` may carry a one-line reason).
_STATUS_LINE_RE = re.compile(
    r"^\s*Status\s*[:：]\s*(proposed|implemented|rejected)"
)

# Top-of-file Agent Note title. The title itself is intentionally
# permissive: any non-empty text after ``Agent Note:``.
_TITLE_LINE_RE = re.compile(r"^#\s+Agent Note\s*[:：]\s*\S.*$")

# Section markers we require in the body (per README §3.2 / §3.3).
_PROBLEM_HEADING_RE = re.compile(r"^##\s+Problem\s*$", re.MULTILINE)
_ALTERNATIVES_HEADING_RE = re.compile(
    r"^##\s+Alternatives considered\s*$", re.MULTILINE
)


# ── data types ────────────────────────────────────────────────────


@dataclass
class Note:
    """One Agent Note file plus its parsed shape."""

    path: Path
    lifecycle: str  # "proposed" | "implemented" | "rejected" | "archived"
    body: str


@dataclass
class Finding:
    severity: str  # "error" | "warn"
    code: str
    where: str
    message: str
    line: int | None = None


# ── file walking ──────────────────────────────────────────────────


def _walk_notes(notes_root: Path) -> tuple[list[Note], list[Finding]]:
    """Return (notes, findings) by walking ``notes_root`` recursively."""
    notes: list[Note] = []
    findings: list[Finding] = []

    if not notes_root.exists():
        findings.append(
            Finding("error", "notes-root-missing",
                    str(notes_root.relative_to(_ROOT)),
                    "docs/notes/ directory does not exist; "
                    "create it before running this check")
        )
        return notes, findings

    # 1. Validate the lifecycle root: only allowed top-level entries.
    lifecycle_dirs: dict[str, Path] = {}
    for entry in sorted(notes_root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name in _LIFECYCLE_DIRS or entry.name == "archived":
                lifecycle_dirs[entry.name] = entry
            elif entry.name in _NON_NOTE_TOP_DIRS:
                # ``templates/`` and ``archived/`` are not lifecycle dirs but
                # are explicitly allowed (README §2.1). They hold non-note
                # artifacts (skeletons, frozen notes).
                pass
            else:
                findings.append(
                    Finding("error", "bad-lifecycle-dir",
                            str(entry.relative_to(_ROOT)),
                            f"top-level dir must be one of "
                            f"{[*sorted(_LIFECYCLE_DIRS), *sorted(_NON_NOTE_TOP_DIRS)]}; got "
                            f"{entry.name!r}")
                )
        elif entry.is_file():
            if (entry.name not in _NOTES_ROOT_FILES
                    and not _NOTES_ROOT_FILE_RE.match(entry.name)):
                findings.append(
                    Finding("error", "bad-notes-root-file",
                            str(entry.relative_to(_ROOT)),
                            f"file at docs/notes/ root must be one of "
                            f"{sorted(_NOTES_ROOT_FILES)} or match "
                            f"audit-YYYY-MM-DD.md; got {entry.name!r}")
                )
            if entry.name == "INDEX.md":
                findings.append(
                    Finding("error", "forbidden-index",
                            str(entry.relative_to(_ROOT)),
                            "INDEX.md forbidden at any depth; "
                            "centralised indexes are disallowed")
                )

    # 2. For each lifecycle dir, validate second-level class dirs.
    for lc_name, lc_dir in lifecycle_dirs.items():
        for entry in sorted(lc_dir.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name not in _CLASS_DIRS:
                    findings.append(
                        Finding("error", "bad-class-dir",
                                str(entry.relative_to(_ROOT)),
                                f"second-level dir under {lc_name}/ must be "
                                f"one of {sorted(_CLASS_DIRS)}; got "
                                f"{entry.name!r}")
                    )
                    continue
                # Recurse to collect note files.
                _collect_notes(entry, lc_name, notes, findings)
            elif entry.is_file():
                if entry.name not in _LIFECYCLE_ROOT_FILES:
                    findings.append(
                        Finding("error", "bad-lifecycle-root-file",
                                str(entry.relative_to(_ROOT)),
                                f"file at lifecycle root must be one of "
                                f"{sorted(_LIFECYCLE_ROOT_FILES)}; got "
                                f"{entry.name!r}")
                    )
                if entry.name == "INDEX.md":
                    findings.append(
                        Finding("error", "forbidden-index",
                                str(entry.relative_to(_ROOT)),
                                "INDEX.md forbidden at any depth; "
                                "centralised indexes are disallowed")
                    )

    return notes, findings


def _collect_notes(class_dir: Path,
                   lifecycle: str,
                   notes: list[Note],
                   findings: list[Finding]) -> None:
    """Walk a ``{lifecycle}/{class}/`` subtree, collect Note records."""
    for path in sorted(class_dir.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(_ROOT)
        # Forbid INDEX.md anywhere in the tree.
        if path.name == "INDEX.md":
            findings.append(
                Finding("error", "forbidden-index", str(rel),
                        "INDEX.md forbidden at any depth; "
                        "centralised indexes are disallowed")
            )
            continue
        # Filename pattern check.
        if not _FILENAME_RE.match(path.name):
            findings.append(
                Finding("error", "bad-filename", str(rel),
                        "filename does not match YYYY-MM-DD-<topic>.md")
            )
            # Still record so the header scan can surface additional issues.
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover — defensive only
            findings.append(
                Finding("error", "unreadable", str(rel), str(exc))
            )
            continue
        notes.append(Note(path=path, lifecycle=lifecycle, body=body))


# ── per-note checks ──────────────────────────────────────────────


def _check_note(note: Note) -> list[Finding]:
    """Run header / body / status checks against a single note."""
    findings: list[Finding] = []
    rel = str(note.path.relative_to(_ROOT))
    lines = note.body.splitlines()

    # archived/ is exempt from header / Status checks — its format is
    # sealed per README §3.2 (frozen). Only filename / INDEX rules apply.
    if note.lifecycle == "archived":
        return findings

    # Header three-line: line 1 is title, line 2 is blank, line 3 is Status.
    title_line = lines[0] if lines else ""
    if not _TITLE_LINE_RE.match(title_line):
        # The title may NOT be just ``Agent Note:`` — README §3.1 demands
        # ``Agent Note: <title>``.
        findings.append(
            Finding("error", "bad-header-title", rel,
                    f"line 1 must be '# Agent Note: <title>'; got: "
                    f"{title_line!r}")
        )
        # Without a parseable header we cannot validate Status consistency
        # or body sections further, so stop here.
        return findings

    # Blank line between title and Status.
    if len(lines) < 3 or lines[1].strip() != "":
        findings.append(
            Finding("error", "bad-header-blank", rel,
                    "line 2 must be blank (header three-line)")
        )

    # Status: line on line 3.
    status_match = None
    if len(lines) >= 3:
        status_match = _STATUS_LINE_RE.match(lines[2])
    if status_match is None:
        findings.append(
            Finding("error", "missing-status", rel,
                    "line 3 must be 'Status: <proposed|implemented|"
                    "rejected>' (or with ' — <reason>' tail)")
        )
    else:
        declared = status_match.group(1)
        if declared != note.lifecycle:
            findings.append(
                Finding("error", "status-mismatch", rel,
                        f"Status: declares {declared!r} but file lives "
                        f"under {note.lifecycle!r}/; "
                        f"move file or fix the Status line")
            )

    # Body must contain ## Problem and ## Alternatives considered.
    if not _PROBLEM_HEADING_RE.search(note.body):
        findings.append(
            Finding("error", "missing-problem", rel,
                    "body must contain '## Problem' (required opener)")
        )
    if not _ALTERNATIVES_HEADING_RE.search(note.body):
        findings.append(
            Finding("error", "missing-alternatives", rel,
                    "body must contain '## Alternatives considered' "
                    "(per README §3.3)")
        )

    return findings


# ── reporting ─────────────────────────────────────────────────────


def _render_markdown(findings: list[Finding]) -> str:
    out: list[str] = []
    out.append("# Notes Tree Check\n\n")
    out.append("Generated by `scripts/check_notes_tree.py`. Read-only.\n\n")
    out.append("**Scope**: structural & format validation only. Per\n")
    out.append("[`docs/notes/README.md`](../notes/README.md), archived/\n")
    out.append("files follow their frozen shape and are exempt from header\n")
    out.append("and Status checks. This script does NOT touch `docs/adr/`.\n\n")

    if not findings:
        out.append("No issues found.\n")
        return "".join(out)

    out.append(f"## Findings ({len(findings)})\n\n")
    out.append("| Severity | Code | Where | Line | Message |\n")
    out.append("|---|---|---|---|---|\n")
    for f in sorted(findings,
                    key=lambda x: (x.severity != "error", x.code, x.where)):
        line = str(f.line) if f.line is not None else "-"
        msg = f.message.replace("|", "\\|")
        out.append(f"| {f.severity} | `{f.code}` | {f.where} | {line} | {msg} |\n")
    return "".join(out)


def _render_json(findings: list[Finding]) -> str:
    payload = {
        "script": "check_notes_tree.py",
        "findings": [
            {
                "severity": f.severity,
                "code": f.code,
                "where": f.where,
                "line": f.line,
                "message": f.message,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# ── main ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=_ROOT / "docs" / "notes",
        help="notes directory to scan (default: docs/notes)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit JSON instead of a markdown table (for CI)",
    )
    args = parser.parse_args(argv)

    try:
        notes, findings = _walk_notes(args.root)
        for note in notes:
            findings.extend(_check_note(note))
    except Exception as exc:  # pragma: no cover — defensive only
        print(f"fatal: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        sys.stdout.write(_render_json(findings))
    else:
        sys.stdout.write(_render_markdown(findings))

    # Exit 1 only on ERROR findings (the script's findings are
    # structural — there are no warnings). An empty list is exit 0.
    has_errors = any(f.severity == "error" for f in findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
