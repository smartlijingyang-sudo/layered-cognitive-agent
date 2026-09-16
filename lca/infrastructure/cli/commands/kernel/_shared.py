"""Shared helpers used by multiple command modules.

These are CLI-adjacent utilities (context construction, journal path resolution,
report rendering) that don't belong to any single command group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.config.config import OpsConfig
from lca.infrastructure.cli.console.console import Console, ConsoleConfig
from lca.infrastructure.cli.pipeline.pipeline import PipelineContext
from lca.infrastructure.cli.services import build_registry
from lca.infrastructure.cli.state.state import StateStore


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


def resolve_event_ledger_path(jsonl: Path | None, run_id: str | None) -> Path:
    """Resolve the per-run spine ledger (CLI error on miss).

    ``journal.json`` is a ``lca.journal/3.1`` *document* — the folded
    step-tree projection. Reading it line-by-line as a ledger yields zero
    events, so failure-explanation commands that consume
    ``_load_inspector_from_jsonl`` must be pointed at the append-only
    ``<run_id>.spine.jsonl`` instead (ADR-0169: the spine ledger is the
    SSOT). Resolving through :func:`resolve_journal_path` silently handed
    those commands the projection and they reported "no failure found"
    for runs that had failed.
    """
    if jsonl is not None:
        if jsonl.exists():
            return jsonl
        typer.echo(f"No event ledger at --jsonl path: {jsonl}", err=True)
        raise typer.Exit(1)
    if run_id:
        from lca.infrastructure.observability.spine.sinks.naming import (
            spine_filename_for_run,
        )

        spine = Path("traces/runs") / run_id / spine_filename_for_run(run_id)
        if spine.exists():
            return spine
        typer.echo(
            f"No event ledger for run {run_id!r}: expected {spine}. "
            "Without it no failure signal can be read; nothing was reported.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo("resolve_event_ledger_path requires --jsonl or a run_id", err=True)
    raise typer.Exit(1)


def spine_terminal_outcome(spine_path: Path) -> str:
    """Read the LAST ``kernel.run.stop`` event's ``payload.outcome``.

    Mirrors the durable-terminal logic the deleted live-SOP tail loop
    used; we read the spine once after terminal lands rather than
    polling for it. Empty / missing spine returns ``"unknown"`` so
    the report stays well-formed.
    """
    if not spine_path.exists():
        return "unknown"
    last_outcome: str | None = None
    with spine_path.open("rb") as fp:
        for raw in fp:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("execution_point") != "kernel.run.stop":
                continue
            payload = rec.get("payload") or {}
            outcome = payload.get("outcome")
            if isinstance(outcome, str):
                last_outcome = outcome
    return last_outcome or "unknown"


_FAILURE_OUTCOMES = frozenset({"fail", "failed", "failure", "error"})


def run_failure_evidence(ledger_path: Path) -> str | None:
    """Return why this run is known to have failed, or ``None``.

    Two durable sources are consulted because they fail differently:
    the ledger's ``kernel.run.stop`` outcome is the fact-stream record,
    while the sibling ``manifest.json``'s ``session_status`` survives a
    run that died before the kernel wrote its stop event. A diagnostic
    that reports "no failure found" while either says otherwise is the
    silent fallback AGENTS.md §4 forbids, so callers must fail loud on
    a hit.
    """
    outcome = spine_terminal_outcome(ledger_path)
    if outcome.lower() in _FAILURE_OUTCOMES:
        return f"ledger kernel.run.stop outcome={outcome}"
    manifest_path = ledger_path.parent / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    session_status = str(manifest.get("session_status") or "")
    if session_status.lower() in _FAILURE_OUTCOMES:
        return f"manifest session_status={session_status}"
    doctor = (manifest.get("extra") or {}).get("doctor_report") or {}
    doctor_status = str(doctor.get("status") or "") if isinstance(doctor, dict) else ""
    if doctor_status.lower() in _FAILURE_OUTCOMES:
        return f"manifest doctor_report.status={doctor_status}"
    return None


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
    """Return the ``run_id`` whose ``traces/runs/<run_id>`` dir has the newest mtime.

    The run directory mtime is the sole signal; no pointer file is read or
    written. Returns ``None`` if ``traces/runs/`` does not exist or is empty.
    """
    root = traces_root if traces_root is not None else Path("traces")
    runs_root = root / "runs"
    if not runs_root.exists():
        return None
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
