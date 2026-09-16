"""``lca-ops runs health <run_id>`` — one-line health answer from RunHealthReport.

Per spec §2.4 / Task 1.11: exposes the RunHealthReport typed contract as a
CLI command, so agents can get a single-line answer to "did the run actually
work?" without parsing spine.jsonl.

Output is JSON by default. The `overall` field is the worst status across
conditions (priority: failed > degraded > unknown > ok).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from lca.contracts.observability.health.report import (
    RunHealthReport,
    RunHealthSummary,
)
from lca.plugins.observability.health.run_health_fold import fold_run_health

_DEFAULT_TRACES_ROOT = Path("traces")

_STATUS_PRIORITY = {"failed": 0, "degraded": 1, "unknown": 2, "ok": 3}


def _worst_status(conditions) -> str:
    if not conditions:
        return "unknown"
    statuses = {c.status for c in conditions if hasattr(c, "status") and c.status in _STATUS_PRIORITY}
    if not statuses:
        return "unknown"
    return min(statuses, key=lambda s: _STATUS_PRIORITY.get(s, 99))


def register(app: typer.Typer) -> None:
    """Mount `runs health` under the runs sub-app."""

    @app.command(
        name="health",
        help=(
            "One-line health answer from RunHealthReport. Reads the run's "
            "spine.jsonl, folds through the 8 registered HealthDerivers, and "
            "prints a JSON report with the worst status per type + per "
            "condition + evidence_refs pointing to the spine events."
        ),
    )
    def health_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        spine_path: Optional[Path] = typer.Option(
            None,
            "--spine",
            help="Override spine file path. Default: traces/runs/<run_id>/<run_id>.spine.jsonl",
        ),
    ) -> None:
        if spine_path is None:
            spine_path = _DEFAULT_TRACES_ROOT / "runs" / run_id / f"{run_id}.spine.jsonl"
        if not spine_path.exists():
            typer.echo(
                f"error: spine file not found: {spine_path}",
                err=True,
            )
            raise typer.Exit(code=2)

        try:
            report = fold_run_health(spine_path)
        except Exception as exc:
            typer.echo(
                f"error: fold_run_health raised {type(exc).__name__}: {exc}",
                err=True,
            )
            raise typer.Exit(code=3) from exc

        payload = {
            "schema_version": report.schema_version,
            "run_id": report.run_id,
            "overall": _worst_status(report.conditions),
            "by_type": report.summary.by_type,
            "conditions": [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "evidence_refs": [
                        {
                            "run_id": ref.run_id,
                            "event_id": ref.event_id,
                            "execution_point": ref.execution_point,
                            "seq": ref.seq,
                        }
                        for ref in c.evidence_refs
                    ],
                    "observed_at": c.observed_at,
                }
                for c in report.conditions
            ],
        }
        typer.echo(json.dumps(payload, indent=2, default=str))
