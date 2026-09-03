"""Notes CLI commands (Agent Notes tree + ADR audit).

Thin wrappers around the read-only scripts under ``scripts/``:

* ``notes-check`` → ``scripts/check_notes_tree.py``
* ``notes-audit`` → ``scripts/audit_adr_health.py`` (writes to
  ``docs/notes/audit-YYYY-MM-DD.md``)
* ``notes-slop``  → ``scripts/verify_doc_slop.py``
* ``notes-list``  → walks ``docs/notes/`` directly (no subprocess)

Exit codes pass through; JSON mode forwards to scripts that support it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import resolve_repo_root

# Lifecycle closed set (must mirror ``scripts/check_notes_tree.py``).
# Notes under these directories carry a ``Status: <lifecycle>`` line.
_NOTE_LIFECYCLE_DIRS: frozenset[str] = frozenset(
    {"proposed", "implemented", "rejected"}
)

# Non-note top-level dirs in ``docs/notes/``: reported with their own
# ``lifecycle`` value, exempt from header checks.
_NOTE_NON_NOTE_DIRS: frozenset[str] = frozenset(
    {"archived", "templates"}
)

# Class closed set (second level under each lifecycle dir).
_NOTE_CLASS_DIRS: frozenset[str] = frozenset(
    {"contract", "primitive", "seam", "profile", "runbook", "postmortem"}
)

_STATUS_LINE_RE = re.compile(
    r"^\s*Status\s*[:：]\s*(proposed|implemented|rejected)\b"
)


def _walk_notes_tree(
    notes_root: Path, repo_root: Path
) -> list[dict[str, object]]:
    """Collect one record per ``.md`` file under ``notes_root``."""
    records: list[dict[str, object]] = []
    for md in sorted(notes_root.rglob("*.md")):
        rel = md.relative_to(repo_root)
        # ``rel`` looks like ``docs/notes/...``, so the 3rd element is the
        # top-level dir under ``docs/notes/`` (or absent for files living
        # at the notes root).
        parts = rel.parts
        # Skip dotfiles in any segment.
        if any(part.startswith(".") for part in parts):
            continue

        top: str | None = parts[2] if len(parts) >= 3 else None
        second: str | None = parts[3] if len(parts) >= 4 else None

        lifecycle: str | None
        class_dir: str | None
        if top is None:
            # ``docs/notes/README.md`` / ``AGENTS.md`` / ``CLAUDE.md`` /
            # ``audit-YYYY-MM-DD.md`` — at notes root, lifecycle/class None.
            lifecycle = None
            class_dir = None
        elif top in _NOTE_LIFECYCLE_DIRS:
            lifecycle = top
            # Lifecycle-root ``AGENTS.md`` / ``CLAUDE.md`` are not a class.
            class_dir = second if (second is not None and second in _NOTE_CLASS_DIRS) else None
        elif top in _NOTE_NON_NOTE_DIRS:
            # ``archived/`` and ``templates/`` exempt from header checks but
            # surface their bucket so callers can tell them apart.
            lifecycle = top
            class_dir = None
        else:
            # Unknown intermediate — still record it but flag lifecycle as
            # None so the agent can see the anomaly.
            lifecycle = None
            class_dir = None

        has_status = False
        status_value: str | None = None
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        # Match the same shape as ``scripts/check_notes_tree.py``:
        # header three-line — line 1 title, line 2 blank, line 3 Status.
        lines = text.splitlines()
        if len(lines) >= 3 and lines[1].strip() == "":
            status_match = _STATUS_LINE_RE.match(lines[2])
            if status_match is not None:
                has_status = True
                status_value = status_match.group(1)

        records.append(
            {
                "path": str(rel),
                "lifecycle": lifecycle,
                "class": class_dir,
                "filename": md.stem,
                "has_status_line": has_status,
                "status_value": status_value,
            }
        )
    return records


def _run_subprocess(
    *args: str, json_mode: bool, repo_root: Path
) -> subprocess.CompletedProcess[str]:
    """Run ``python <script>`` under the repo root and return the proc."""
    return subprocess.run(  # noqa: S603  -- args are hardcoded script paths
        [sys.executable, *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


def register(app: typer.Typer) -> None:
    """Register notes commands on the typer app."""

    @app.command(name="notes-check")
    def notes_check_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Run ``scripts/check_notes_tree.py`` (Agent Notes structural validator)."""
        repo_root = resolve_repo_root()
        cmd: list[str] = ["scripts/check_notes_tree.py"]
        if json_mode:
            cmd.append("--json")
        proc = _run_subprocess(*cmd, json_mode=json_mode, repo_root=repo_root)
        if json_mode:
            sys.stdout.write(proc.stdout)
        else:
            print("# notes-check")
            if proc.stdout:
                sys.stdout.write(proc.stdout)
                if not proc.stdout.endswith("\n"):
                    print()
            if proc.stderr.strip():
                print()
                print("stderr:", file=sys.stderr)
                sys.stderr.write(proc.stderr)
        raise typer.Exit(proc.returncode)

    # Alias ``check-notes-tree`` (matches the script's stem).
    app.command(name="check-notes-tree")(notes_check_cmd)

    @app.command(name="notes-audit")
    def notes_audit_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Run ``scripts/audit_adr_health.py`` and write a daily report."""
        repo_root = resolve_repo_root()
        today = date.today().isoformat()
        report_path = repo_root / "docs" / "notes" / f"audit-{today}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Script doesn't support ``--json`` yet — pass None to keep the
        # contract honest (only forward flags the script accepts).
        proc = subprocess.run(  # noqa: S603  -- hardcoded script path
            [
                sys.executable,
                "scripts/audit_adr_health.py",
                "--out",
                str(report_path),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        rc = proc.returncode
        if json_mode:
            sys.stdout.write(
                json.dumps(
                    {
                        "script_rc": rc,
                        "report_path": str(report_path),
                        "stderr": proc.stderr.strip(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )
        else:
            print(f"wrote {report_path}")
            if report_path.exists():
                try:
                    preview = report_path.read_text(encoding="utf-8")
                except OSError as exc:
                    print(f"(failed to read summary: {exc})")
                else:
                    head = preview.splitlines()[:30]
                    print()
                    for line in head:
                        print(line)
                    if len(preview.splitlines()) > 30:
                        print("... (truncated)")

        raise typer.Exit(rc)

    @app.command(name="notes-slop")
    def notes_slop_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Run ``scripts/verify_doc_slop.py`` (stale-time / change-log lint)."""
        repo_root = resolve_repo_root()
        cmd = ["scripts/verify_doc_slop.py"]
        if json_mode:
            cmd.append("--json")
        proc = _run_subprocess(*cmd, json_mode=json_mode, repo_root=repo_root)
        if json_mode:
            sys.stdout.write(proc.stdout)
        else:
            print("# notes-slop")
            if proc.stdout:
                sys.stdout.write(proc.stdout)
                if not proc.stdout.endswith("\n"):
                    print()
            if proc.stderr.strip():
                print()
                print("stderr:", file=sys.stderr)
                sys.stderr.write(proc.stderr)
        raise typer.Exit(proc.returncode)

    # Alias ``check-doc-slop`` (matches the script's stem).
    app.command(name="check-doc-slop")(notes_slop_cmd)

    @app.command(name="notes-list")
    def notes_list_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Walk ``docs/notes/`` and emit one record per ``.md`` file."""
        repo_root = resolve_repo_root()
        notes_root = repo_root / "docs" / "notes"
        if not notes_root.is_dir():
            print(
                f"docs/notes/ not found under {repo_root}",
                file=sys.stderr,
            )
            raise typer.Exit(1)
        records = _walk_notes_tree(notes_root, repo_root)

        if json_mode:
            sys.stdout.write(
                json.dumps(records, indent=2, ensure_ascii=False) + "\n"
            )
            raise typer.Exit(0)

        # Human mode: a markdown table.
        print(f"# docs/notes/ inventory ({len(records)} files)\n")
        print("| path | lifecycle | class | status_value |")
        print("|---|---|---|---|")
        for record in records:
            path = str(record["path"])
            lifecycle = record["lifecycle"] or "—"
            class_dir = record["class"] or "—"
            status = record["status_value"] or "—"
            print(f"| {path} | {lifecycle} | {class_dir} | {status} |")
        raise typer.Exit(0)
