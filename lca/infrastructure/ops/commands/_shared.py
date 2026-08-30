"""Shared helpers used by multiple command modules.

These are CLI-adjacent utilities (context construction, journal path resolution,
report rendering) that don't belong to any single command group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.ops.config import OpsConfig
from lca.infrastructure.ops.console import Console, ConsoleConfig
from lca.infrastructure.ops.pipeline import PipelineContext
from lca.infrastructure.ops.services import build_registry
from lca.infrastructure.ops.state import StateStore


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


def resolve_journal_path(jsonl: Path | None, run_id: str | None) -> Path:
    """Resolve journal.jsonl: explicit → ``traces/lca_journal.jsonl`` → per-run."""
    if jsonl is not None:
        if not jsonl.exists():
            print(f"No journal file at {jsonl}")
            raise typer.Exit(1)
        return jsonl
    default_global = Path("traces/lca_journal.jsonl")
    if default_global.exists():
        return default_global
    if run_id is not None:
        per_run = Path(f"traces/runs/{run_id}/journal.jsonl")
        if per_run.exists():
            return per_run
    print(f"No journal file found (tried {default_global} and traces/runs/<id>/journal.jsonl)")
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
    """Pick the journal jsonl file to scan.

    Resolution order:
    1. Explicit ``--journal`` argument.
    2. ``traces/runs/<trace_id>.journal`` when ``--trace-id`` is set.
    3. ``traces/lca_journal.jsonl`` (the durable global fact stream).
    """
    if explicit is not None:
        return explicit
    if trace_id:
        candidate = Path("traces/runs") / f"{trace_id}.journal"
        if candidate.exists():
            return candidate
    fallback = Path("traces/lca_journal.jsonl")
    if fallback.exists():
        return fallback
    return None
