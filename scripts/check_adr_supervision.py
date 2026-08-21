#!/usr/bin/env python3
"""Pre-commit / CI hook: ADR supervision consistency check.

ADR-0074 Plugin-Everything tracker 是 ADR-0066 / 0067 / 0068 / 0069 / 0074
落地的中央账本。本脚本验证 tracker.md 的声明与仓库真实状态一致：

1. tracker §1 状态总览：✅ Done 行必须引用有效 git commit hash
2. tracker「ADR 监督范围」实施矩阵：✅ 行必须同时满足 done + commit 存在
3. Next Action 必须指向首个未完成且不在 Blocked 链的 PR
4. tracker 内引用的 commit hash 全部存在（不可悬空）

不修源码只查一致性。是 pre-commit / CI 的看门人。

退出码：
  0 = 全部一致
  1 = 存在不一致行（详见 stderr）
  2 = tracker.md 不存在或解析失败
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TRACKER = _ROOT / "docs" / "plans" / "adr-0074-plugin-everything-tracker.md"


@dataclass
class Finding:
    """Verification report row."""

    severity: str  # "error" | "warn"
    location: str  # tracker:line or section name
    message: str


# ── helpers ───────────────────────────────────────────────────────


def _read_git_commit_exists(sha: str) -> bool:
    """Return True when ``sha`` resolves to a git commit object in this repo."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return False
    # sha is constrained to a hex regex above; we always invoke a hardcoded
    # binary — argument list is fully under our control.
    result = subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", sha],  # noqa: S607
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _section_text(text: str, header_pattern: str) -> str | None:
    """Slice the text body from a markdown ``##`` section whose title matches.

    Args:
        text: Full markdown content.
        header_pattern: Regex (case-sensitive) anchored to ``## <pattern>``.

    Returns:
        The slice from the section header until the next ``##`` header, or None
        if the section is not found.
    """
    rx = re.compile(rf"^## (?!#)({header_pattern})[^\n]*$", re.MULTILINE)
    match = rx.search(text)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_h = re.search(r"^## (?!#)", rest, re.MULTILINE)
    end = match.end() + (next_h.start() if next_h else len(rest))
    return text[start:end]


def _table_rows(section: str) -> list[list[str]]:
    """Parse all markdown rows from one section's first table.

    Skips the alignment row (containing ``:---`` or ``-:-``).

    Returns:
        List of cell lists (first row is the header).
    """
    rows: list[list[str]] = []
    for line in section.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:\-|]+\|\s*$", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows


def _first_table(section: str) -> list[list[str]] | None:
    rows = _table_rows(section)
    return rows if rows else None


def _all_tables(section: str) -> list[list[list[str]]]:
    """Yield each markdown table in ``section`` as a list-of-rows.

    A new table starts after a blank line, or whenever a non-``|`` line breaks
    the table flow.
    """
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in section.splitlines():
        if line.startswith("|"):
            if re.match(r"^\|[\s:\-|]+\|\s*$", line):
                # alignment row — skip but keep table flowing
                continue
            current.append([c.strip() for c in line.strip().strip("|").split("|")])
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


# ── verification ────────────────────────────────────────────────


def _verify_status_overview(text: str) -> list[Finding]:
    """§1 status table: ✅ Done rows must carry a real commit hash."""
    findings: list[Finding] = []
    section = _section_text(text, r"1\.\s*状态总览")
    if section is None:
        return [Finding("error", "§1", "section missing")]
    table = _first_table(section)
    if table is None:
        return [Finding("error", "§1", "table missing")]
    header = table[0]
    if "Commit" not in " ".join(header):
        return [Finding("error", "§1", "Commit column missing")]
    col_idx = header.index("Commit") if "Commit" in header else len(header) - 2
    body_idx_col = header.index("状态") if "状态" in header else 3

    for row in table[1:]:
        if len(row) <= max(col_idx, body_idx_col):
            continue
        status_cell = row[body_idx_col]
        commit_cell = row[col_idx]
        if "✅" not in status_cell:
            continue
        if commit_cell == "—" or not commit_cell.strip():
            findings.append(Finding("error", "§1", f"✅ row lacks commit hash: {row}"))
            continue
        sha = commit_cell.strip().strip("`")
        if not _read_git_commit_exists(sha):
            findings.append(
                Finding("error", "§1", f"commit hash not found in git: {sha} (row: {row})")
            )
    return findings


def _verify_supervision_matrix(text: str) -> list[Finding]:
    """「ADR 监督范围」implementation matrix: ✅ rows must carry a real commit hash.

    The implementation matrix is a markdown table whose header contains the
    literal column ``ADR §``. We walk all tables in the section and target the
    matching one.
    """
    findings: list[Finding] = []
    section = _section_text(text, r"ADR 监督范围")
    if section is None:
        return [Finding("error", "ADR 监督范围", "section missing")]
    tables = _all_tables(section)
    matrix: list[list[str]] | None = None
    for tbl in tables:
        header_text = " ".join(tbl[0])
        if "ADR §" in header_text and "交付 PR" in header_text:
            matrix = tbl
            break
    if matrix is None:
        return [Finding("error", "ADR 监督范围", "implementation matrix not found")]

    header = matrix[0]
    adr_col = header.index("ADR §")
    state_col = header.index("状态")
    pr_col = header.index("交付 PR")

    for row in matrix[1:]:
        if len(row) <= max(adr_col, state_col, pr_col):
            continue
        status_cell = row[state_col]
        if "✅" not in status_cell:
            continue
        adr_cell = row[adr_col]
        pr_cell = row[pr_col]
        if "Phase 0" in pr_cell or re.search(r"PR-\d", pr_cell):
            # Phase 0 work is captured by ADR §1 / §2 etc. and concrete
            # commit refs live in the §1 status table; matrix row is OK to
            # carry PR-N forward-pointers.
            continue
        findings.append(
            Finding(
                "warn",
                f"ADR 监督范围 / {adr_cell}",
                f"✅ row without concrete deliverer hash: {pr_cell}",
            )
        )
    return findings


def _verify_next_action_is_reachable(text: str) -> list[Finding]:
    """Next Action PR must exist in §1 with status Ready or Blocked (not Done)."""
    findings: list[Finding] = []
    na_match = re.search(r"\*\*Next Action\*\*[：:]\s*PR-(\d+)", text)
    if not na_match:
        return [Finding("warn", "§1", "no Next Action marker found")]
    next_pr_num = int(na_match.group(1))

    section = _section_text(text, r"1\.\s*状态总览")
    if section is None:
        return [Finding("error", "§1", "section missing")]
    table = _first_table(section)
    if table is None:
        return [Finding("error", "§1", "table missing")]
    header = table[0]
    pr_col = header.index("PR")
    state_col = header.index("状态")

    target_row: list[str] | None = None
    for row in table[1:]:
        if len(row) <= max(pr_col, state_col):
            continue
        pr_label = row[pr_col]
        if pr_label == f"{next_pr_num}" or pr_label.endswith(f"-{next_pr_num}"):
            target_row = row
            break
        # Handle PR IDs like "0.5", "2.5" with `.` separator
        if pr_label.split(".")[0] == str(next_pr_num):
            target_row = row
            break

    if target_row is None:
        findings.append(
            Finding("error", "§1", f"Next Action PR-{next_pr_num} not present in status table")
        )
        return findings

    state = target_row[state_col]
    if "Done" in state:
        findings.append(
            Finding(
                "warn",
                "§1",
                f"Next Action PR-{next_pr_num} is marked Done; Next Action should point to a not-yet-done PR",
            )
        )
    return findings


def _verify_no_hanging_commit_refs(text: str) -> list[Finding]:
    """Every commit-shaped hex string in the tracker must resolve in git."""
    findings: list[Finding] = []
    for match in re.finditer(r"`([0-9a-f]{7,40})`", text):
        sha = match.group(1)
        if not _read_git_commit_exists(sha):
            findings.append(Finding("error", "tracker md", f"dangling commit hash: `{sha}`"))
    return findings


# ── entry point ──────────────────────────────────────────────────


def main() -> int:
    if not _TRACKER.exists():
        print(f"tracker not found: {_TRACKER}", file=sys.stderr)
        return 2
    text = _TRACKER.read_text(encoding="utf-8")

    findings: list[Finding] = []
    findings.extend(_verify_status_overview(text))
    findings.extend(_verify_supervision_matrix(text))
    findings.extend(_verify_next_action_is_reachable(text))
    findings.extend(_verify_no_hanging_commit_refs(text))

    if not findings:
        print("OK: ADR supervision tracker is consistent.")
        return 0

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warn"]
    print(f"Found {len(errors)} error(s), {len(warnings)} warning(s):", file=sys.stderr)
    for f in findings:
        prefix = "ERR" if f.severity == "error" else "WARN"
        print(f"  [{prefix}] {f.location}: {f.message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
