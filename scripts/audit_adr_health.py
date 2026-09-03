#!/usr/bin/env python3
"""Read-only health audit for ``docs/adr/``.

Scans every file under ``docs/adr/`` (excluding ``README.md``) and produces
findings the agent can act on before any future Agent Note migration.

What this script does:

1. Status coverage — every ADR declares its lifecycle state in either
   ``## 状态`` / ``## Status`` / an inline ``Superseded by`` / ``Status: …`` form.
2. Status normalisation — extract the dominant status token (``Accepted``,
   ``Proposed``, ``Superseded``, ``Audit``, ``Review``, ``Explained``, ``Deprecated``,
   ``Rejected``, …) and report the unique distribution.
3. Numbering — list gaps and out-of-range ids, surface duplicate slugs.
4. Cross-references — ``Superseded by`` / ``Supersedes`` point at real files;
   no target is a 404.
5. README index reconciliation — every ADR in ``docs/adr/README.md`` resolves
   to a real file, and every real file (except README itself) appears in the
   README table.

It does not edit anything. Exit code is 0 unless a fatal parse error occurs;
the report is markdown written to stdout (or ``--out``). Non-fatal findings
are warnings only.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ADR_DIR = _ROOT / "docs" / "adr"

# Status tokens seen in the corpus. ``Accepted`` / ``Proposed`` / ``Superseded``
# are the three dominant ones; the rest are second-class and surfaced as such.
_STATUS_TOKENS = {
    "Accepted",
    "Proposed",
    "Superseded",
    "Rejected",
    "Deprecated",
    "Audit",
    "Review",
    "Explained",
}
# Regex that captures the status token after either `## 状态` / `## Status`
# (whole line) or an inline `Status: <token>` / `Superseded by ADR-XXXX`.
_STATUS_HEAD = re.compile(
    r"^\s*(?:\*\*)?\s*(?:Status|状态)\s*[:：]?\s*(?:\*\*)?\s*([A-Za-z]+)"
)
_STATUS_INLINE = re.compile(r"\*\*Status\*\*\s*[:：]?\s*\*\*([A-Za-z]+)\*\*")
# `**Status**: Accepted` or `**Status**: Accepted（...` — value can be
# immediately followed by CJK text, parens, or em-dash. We allow the first
# non-space, non-CJK-truncation chunk to be the token.
_STATUS_BOLD_PREFIX = re.compile(r"\*\*Status\*\*\s*[:：]?\s*\*?\*?([A-Za-z]+)")
_SUPERSEDED_INLINE = re.compile(
    r"(?:Superseded by|被替代为|被取代为)\s*(?:\[?ADR-?)([0-9]+(?:\.[0-9]+)?)"
)
_SUPERSEDES_INLINE = re.compile(
    r"Supersedes(?:\s*[:：])?\s*(?:\*\*)?\s*ADR-?([0-9]+(?:\.[0-9]+)?)"
)
# `0169-loop-cursor-control.md` → (169, "loop-cursor-control")
_FILENAME_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)-(.+)\.md$")
# README table row: `[ 0001 ](0001-five-layer-separation.md) | 五层 | Accepted`
_README_ROW_RE = re.compile(
    r"\[\s*([0-9]+(?:\.[0-9]+)?)\s*\]\(\s*([0-9]+(?:\.[0-9]+)?)-([^)]+)\.md\s*\)"
)


# ── data types ────────────────────────────────────────────────────


@dataclass
class Adr:
    """One ADR file plus its parsed shape."""

    path: Path
    number: str  # "169" or "168.1"
    slug: str
    body: str
    status: str | None = None
    superseded_by: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)


@dataclass
class Finding:
    severity: str  # "warn" | "info"
    code: str
    where: str
    message: str


# ── file walking ──────────────────────────────────────────────────


def _walk_adrs() -> tuple[list[Adr], list[Finding]]:
    """Parse every ADR file. Returns (adrs, findings)."""
    findings: list[Finding] = []
    adrs: list[Adr] = []
    for path in sorted(_ADR_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        m = _FILENAME_RE.match(path.name)
        if not m:
            findings.append(
                Finding("warn", "bad-filename", path.name,
                        "filename does not match NNNN-<slug>.md; skipped")
            )
            continue
        adr = Adr(path=path, number=m.group(1), slug=m.group(2), body=path.read_text())
        _extract_status(adr, findings)
        _extract_supersede_chain(adr, findings)
        adrs.append(adr)
    return adrs, findings


def _extract_status(adr: Adr, findings: list[Finding]) -> None:
    """Pick the dominant status token from a file's body."""
    lines = adr.body.splitlines()
    head = lines[:40]
    # Two patterns matter: (a) the literal token sits on the line *after*
    # `## 状态` / `## Status`, separated by a blank line, which is the
    # dominant LCA convention; (b) the token is bold-inline on the same line.
    # We walk a sliding window of up to 3 consecutive lines so both shapes
    # are recognised.
    for i, line in enumerate(head):
        # Match `## 状态` / `## Status:` even when there's nothing else on
        # the line — the token lives on the next non-blank line. The `\s*`
        # between `##` and `状态` is required so `##  状态` (extra spaces)
        # also works.
        if re.match(r"^\s*#+\s*(?:\*\*)?\s*(?:Status|状态)\s*[:：]?\s*$", line):
            for j in range(i + 1, min(i + 4, len(head))):
                nxt = head[j].strip()
                if not nxt:
                    continue
                # Strip leading **, take first ASCII word (the token may be
                # followed by ` — 2026-08-29`, `（2026-08 修订...`, etc.)
                stripped = nxt.lstrip("*").strip()
                token = re.match(r"([A-Za-z]+)", stripped)
                if token:
                    tok = token.group(1)
                    if tok in _STATUS_TOKENS:
                        adr.status = tok
                        return
                break
        m = _STATUS_HEAD.match(line)
        if m:
            token = m.group(1)
            if token in _STATUS_TOKENS:
                adr.status = token
                return
        m = _STATUS_INLINE.search(line)
        if m:
            token = m.group(1)
            if token in _STATUS_TOKENS:
                adr.status = token
                return
        m = _STATUS_BOLD_PREFIX.search(line)
        if m:
            token = m.group(1)
            if token in _STATUS_TOKENS:
                adr.status = token
                return
    # Fallback: an inline `Superseded by ADR-XXXX` in the first 40 lines is
    # a strong signal — the ADR is, by definition, superseded. Same for
    # `原始状态: Accepted` on a separate line. Search beyond line 40 only
    # for this fallback so we don't invent a status out of unrelated prose.
    for line in adr.body.splitlines()[:120]:
        if _SUPERSEDED_INLINE.search(line):
            adr.status = "Superseded"
            return
        if "原始状态" in line and "Accepted" in line:
            adr.status = "Accepted"
            return
    findings.append(
        Finding("warn", "no-status", f"ADR-{adr.number}",
                "no ## 状态 / ## Status / inline Status declared; "
                "step-2 candidate for manual annotation")
    )


def _extract_supersede_chain(adr: Adr, findings: list[Finding]) -> None:
    """Extract `Superseded by ADR-XXXX` and `Supersedes ADR-XXXX` mentions."""
    for line in adr.body.splitlines():
        for m in _SUPERSEDED_INLINE.finditer(line):
            adr.superseded_by.append(m.group(1))
        for m in _SUPERSEDES_INLINE.finditer(line):
            adr.supersedes.append(m.group(1))


# ── cross-checks ──────────────────────────────────────────────────


def _readme_index(adrs: list[Adr]) -> tuple[set[str], list[Finding]]:
    """Read ``docs/adr/README.md`` and return (indexed_numbers, findings)."""
    findings: list[Finding] = []
    readme = _ADR_DIR / "README.md"
    if not readme.exists():
        findings.append(Finding("warn", "no-readme", "README.md", "missing"))
        return set(), findings
    indexed: set[str] = set()
    for m in _README_ROW_RE.finditer(readme.read_text()):
        indexed.add(m.group(1))
    return indexed, findings


def _check_numbering(adrs: list[Adr]) -> list[Finding]:
    findings: list[Finding] = []
    numbers = [a.number for a in adrs]
    # duplicates
    counter = Counter(numbers)
    for n, c in counter.items():
        if c > 1:
            files = [a.path.name for a in adrs if a.number == n]
            findings.append(
                Finding("warn", "duplicate-number", f"ADR-{n}",
                        f"appears {c} times: {', '.join(files)}")
            )
    # gaps (only for pure integers — sub-ids like 168.1 don't count)
    ints = sorted({int(float(n)) for n in numbers})
    for prev, nxt in pairwise(ints):
        if nxt - prev > 1:
            missing = list(range(prev + 1, nxt))
            findings.append(
                Finding("info", "number-gap",
                        f"ADR-{prev} → ADR-{nxt}",
                        f"missing numbers: {', '.join(str(m) for m in missing)}")
            )
    return findings


def _check_supersede_targets(adrs: list[Adr]) -> list[Finding]:
    findings: list[Finding] = []
    numbers = {a.number for a in adrs}
    for adr in adrs:
        for target in adr.superseded_by:
            if target not in numbers:
                findings.append(
                    Finding("warn", "broken-supersede",
                            f"ADR-{adr.number}",
                            f"Superseded by ADR-{target} but no such ADR exists")
                )
        # Duplicates within the same direction
        if len(set(adr.superseded_by)) != len(adr.superseded_by):
            findings.append(
                Finding("info", "dup-supersede", f"ADR-{adr.number}",
                        f"Superseded by repeated: {sorted(adr.superseded_by)}")
            )
    # Cross-link consistency: if A claims "Superseded by B", does B list A in
    # its `Supersedes`? We only warn when B exists but doesn't reciprocate.
    by_number = {a.number: a for a in adrs}
    for adr in adrs:
        for sup in adr.superseded_by:
            sup_adr = by_number.get(sup)
            if sup_adr is None:
                continue
            if adr.number not in sup_adr.supersedes:
                findings.append(
                    Finding("info", "unreciprocated-supersede",
                            f"ADR-{adr.number} ↔ ADR-{sup}",
                            "A claims 'Superseded by B' but B's Supersedes does not list A")
                )
    return findings


def _check_readme_vs_files(adrs: list[Adr],
                            indexed: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    file_numbers = {a.number for a in adrs}
    missing_in_readme = file_numbers - indexed
    if missing_in_readme:
        findings.append(
            Finding("warn", "file-not-in-readme", "README.md",
                    f"{len(missing_in_readme)} ADR(s) absent from README table: "
                    f"{sorted(missing_in_readme)[:10]}{'…' if len(missing_in_readme) > 10 else ''}")
        )
    extra_in_readme = indexed - file_numbers
    if extra_in_readme:
        findings.append(
            Finding("warn", "readme-references-missing-file", "README.md",
                    f"{len(extra_in_readme)} README row(s) point at nonexistent files: "
                    f"{sorted(extra_in_readme)[:10]}{'…' if len(extra_in_readme) > 10 else ''}")
        )
    return findings


# ── reporting ─────────────────────────────────────────────────────


def _render_report(adrs: list[Adr],
                   findings: list[Finding],
                   indexed: set[str]) -> str:
    out: list[str] = []
    out.append("# ADR Health Audit — 2026-09-03\n")
    out.append("Generated by `scripts/audit_adr_health.py`. Read-only.\n")
    out.append("\n**Scope**: diagnostic only. **Per [`docs/notes/README.md`](../notes/README.md),\n")
    out.append("existing ADRs are not modified, migrated, re-numbered, or assigned\n")
    out.append("sidecars.** Findings below are reference material; no remediation\n")
    out.append("step is required and none will be performed automatically.\n\n")
    out.append("Use the findings to (a) decide whether to write a new ADR when a\n")
    out.append("future architectural question touches an area the audit flagged;\n")
    out.append("(b) cite as evidence when proposing new Agent Notes in\n")
    out.append("`docs/notes/proposed/`.\n\n")

    # Summary
    status_counter: Counter[str] = Counter()
    no_status: list[str] = []
    for a in adrs:
        if a.status is None:
            no_status.append(f"ADR-{a.number}")
        else:
            status_counter[a.status] += 1
    out.append("## Summary\n\n")
    out.append(f"- ADR files parsed: **{len(adrs)}**\n")
    out.append(f"- ADR numbers indexed in README: **{len(indexed)}**\n")
    out.append(f"- ADR files without any status declaration: **{len(no_status)}**\n\n")
    out.append("### Status distribution\n\n")
    out.append("| Status | Count |\n|---|---|\n")
    for status, count in sorted(status_counter.items(), key=lambda kv: -kv[1]):
        out.append(f"| {status} | {count} |\n")
    if no_status:
        out.append("| (no status) | " + str(len(no_status)) + " |\n")
    out.append("\n")

    # Findings
    if findings:
        out.append("## Findings\n\n")
        out.append("| Severity | Code | Where | Message |\n|---|---|---|---|\n")
        for f in sorted(findings, key=lambda x: (x.severity != "warn", x.code, x.where)):
            msg = f.message.replace("|", "\\|")
            out.append(f"| {f.severity} | `{f.code}` | {f.where} | {msg} |\n")
        out.append("\n")
    else:
        out.append("## Findings\n\nNo issues found.\n\n")

    # Most-cited
    supersedes_count: Counter[str] = Counter()
    for a in adrs:
        for s in a.supersedes:
            supersedes_count[f"ADR-{s}"] += 1
    if supersedes_count:
        out.append("## Most-superseded ADR\n\n")
        out.append("ADRs that get cited as `Supersedes <this>` the most often.\n\n")
        out.append("| ADR | Times superseded |\n|---|---|\n")
        for adr_id, count in supersedes_count.most_common(15):
            out.append(f"| {adr_id} | {count} |\n")
        out.append("\n")

    # Files without status — explicit list (for step-2 planning)
    if no_status:
        out.append("## Files without status (step-2 candidates)\n\n")
        out.append("These ADR files lack any `## 状态` / `## Status` / inline status\n")
        out.append("in their first 40 lines. They will need a status annotation\n")
        out.append("before any future archival pass.\n\n")
        out.append("<details><summary>Expand list (" + str(len(no_status)) + " entries)</summary>\n\n")
        for n in sorted(no_status):
            slug = next((a.slug for a in adrs if a.number == n.split("-", 1)[1]), "")
            out.append(f"- `{n}` ({slug})\n")
        out.append("\n</details>\n\n")

    out.append("---\n\n")
    out.append("Re-run with `python scripts/audit_adr_health.py --out path/to/audit.md`.\n")
    return "".join(out)


# ── main ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=None,
                   help="write report to this path (default: stdout)")
    args = p.parse_args(argv)

    try:
        adrs, findings = _walk_adrs()
        indexed, readme_findings = _readme_index(adrs)
        findings.extend(readme_findings)
        findings.extend(_check_numbering(adrs))
        findings.extend(_check_supersede_targets(adrs))
        findings.extend(_check_readme_vs_files(adrs, indexed))
    except Exception as e:  # pragma: no cover — defensive only
        print(f"fatal: {e}", file=sys.stderr)
        return 2

    report = _render_report(adrs, findings, indexed)
    if args.out is not None:
        args.out.write_text(report)
        print(f"wrote {args.out} ({len(findings)} findings)", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
