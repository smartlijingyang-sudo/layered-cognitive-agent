"""Shared helpers used by multiple command modules.

These are CLI-adjacent utilities (context construction, journal path resolution,
report rendering) that don't belong to any single command group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.config import OpsConfig
from lca.infrastructure.cli.console import Console, ConsoleConfig
from lca.infrastructure.cli.pipeline import PipelineContext
from lca.infrastructure.cli.services import build_registry
from lca.infrastructure.cli.state import StateStore


def make_context(
    json_mode: bool = False,
    quiet: bool = False,
    config_path: Path | None = None,
) -> PipelineContext:
    """Build a PipelineContext from CLI options."""
    config = OpsConfig.load(config_path)
    console = Console(ConsoleConfig(json_mode=json_mode, quiet=quiet))
    registry = build_registry(config)
    state = StateStore(config.state_dir)
    return PipelineContext(
        config=config,
        registry=registry,
        state=state,
        console=console,
    )


def _resolve_journal_artifact(
    *,
    jsonl: Path | None,
    trace_id: str | None,
) -> Path | None:
    """Resolve a journal artifact path with run-aware fallback (ADR-0166 S1 / 0167 D3)。

    Resolution order:
    1. Explicit ``--journal`` argument (any caller-provided path wins).
    2. ``traces/runs/<id>/journal.json`` (preferred — lca.journal/3 step story)。
    3. ``traces/runs/<id>/<run_id>.spine.jsonl`` (spine SSOT — ADR-0165.1 / 0167 D11)。

    旧 ``journal.raw.jsonl`` / ``<id>.journal`` / 全局 ``lca_journal.jsonl``
    流式布局已下线 —— 不再回退到任何 legacy artifact。

    Returns the resolved path or ``None`` when nothing was found.
    """
    if jsonl is not None:
        return jsonl if jsonl.exists() else None
    if trace_id:
        nested = Path("traces/runs") / trace_id
        primary = nested / "journal.json"
        if primary.exists():
            return primary
        # ADR-0169 PR-27 L10 + PR-4:默认 <run_id>.spine.jsonl 唯一 SSOT
        from lca.infrastructure.observability.spine.sinks.naming import (
            spine_filename_for_run,
        )

        spine = nested / spine_filename_for_run(trace_id)
        if spine.exists():
            return spine
    return None


def resolve_journal_path(jsonl: Path | None, run_id: str | None) -> Path:
    """Resolve journal artifact path (CLI error on miss)."""
    resolved = _resolve_journal_artifact(jsonl=jsonl, trace_id=run_id)
    if resolved is not None:
        return resolved
    typer.echo(
        "No journal file found (tried --journal, traces/runs/<id>/journal.json, spine ledger)"
    )
    raise typer.Exit(1)


def emit_report(report: object, *, json_mode: bool) -> None:
    """Render a coding-agent tool report: full JSON or ``str()`` fallback."""
    if json_mode:
        typer.echo(json.dumps(report, ensure_ascii=False, default=str))
        return
    if isinstance(report, str):
        typer.echo(report)
        return
    if isinstance(report, dict):
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(report, list):
        for item in report:
            typer.echo(json.dumps(item, ensure_ascii=False, indent=2, default=str))
        return
    typer.echo(str(report))


def resolve_repo_root() -> Path:
    """Return the LCA repository root (where lca-ops was invoked from)."""
    return Path.cwd()


def find_latest_run_id(traces_root: Path | None = None) -> str | None:
    """Return the most recently completed ``run_id``, or ``None``.

    Preference order (matches :mod:`lca.infrastructure.cli.commands.journal`):

    1. ``<traces_root>/latest.json`` (atomic pointer written by
       :class:`FilesystemRunLocator.update_latest_pointer`). Authoritative
       "what was the most recent completed run" signal; avoids mtime
       races where an archived / restored run outranks the live one.
    2. mtime-sorted fallback when the pointer is missing or stale.

    Returns ``None`` if ``traces/runs/`` does not exist or is empty.
    """
    root = traces_root if traces_root is not None else Path("traces")
    runs_root = root / "runs"
    if not runs_root.exists():
        return None
    pointer = root / "latest.json"
    if pointer.is_file():
        try:
            payload = json.loads(pointer.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("kind") == "run_pointer":
            run_id = str(payload.get("run_id", ""))
            if run_id and (runs_root / run_id).is_dir():
                return run_id
    candidates = [p for p in runs_root.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime).name


def audit_roots(*names: str) -> list[Path]:
    """Build scan roots under the repo, ignoring missing dirs."""
    root = resolve_repo_root()
    return [root / name for name in names]


def render_diagnostic_trace_line(item: dict[str, Any]) -> None:
    """Render one diagnostic JSONL record as a compact human-readable row."""
    timestamp = str(item.get("ts", ""))
    category = str(item.get("category", "infra"))
    status = str(item.get("status", "info")).upper()
    plugin = str(item.get("plugin", "-"))
    operation = str(item.get("operation", "-"))
    duration = item.get("duration_ms")
    suffix = f" {duration}ms" if duration is not None else ""
    print(f"{timestamp} [{status:<9}] {category:<10} {plugin:<28} {operation}{suffix}")
    attributes = item.get("attributes") or {}
    output = item.get("output") or {}
    if attributes:
        print(f"  input: {json.dumps(attributes, ensure_ascii=False, sort_keys=True)}")
    if output:
        print(f"  output: {json.dumps(output, ensure_ascii=False, sort_keys=True)}")
    if item.get("error_type"):
        print(f"  error: {item['error_type']}: {item.get('error_message', '')}")


def resolve_diagnose_journal_path(
    explicit: Path | None,
    trace_id: str | None,
) -> Path | None:
    """Pick a journal artifact to scan (returns ``None`` instead of raising)."""
    return _resolve_journal_artifact(jsonl=explicit, trace_id=trace_id)
