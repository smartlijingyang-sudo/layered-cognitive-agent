"""Per-run durable artifact path helpers (ADR-0169 / ADR-0186).

Session persistence observers derive ``run_id`` from the Session delivery
shape ``"{session.id}:{seq}"`` and resolve spine / exceptions paths under
``traces/runs/<run_id>/`` unless a test override ``run_dir`` is supplied.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.observability.spine.sinks.naming import (
    exceptions_filename_for_run,
    spine_filename_for_run,
)

_DEFAULT_RUNS_ROOT = Path("traces") / "runs"


def run_id_from_event_id(event_id: str) -> str:
    """Parse ``run_id`` from ``"{session.id}:{seq}"`` delivery shape."""
    run_id, sep, seq = event_id.rpartition(":")
    if not sep or not run_id or not seq.isdigit():
        raise ValueError(
            f"无法从 event_id={event_id!r} 推导 run_id"
            "（Session 投递契约 '{session.id}:{seq}'）"
        )
    return run_id


def run_dir_for(run_id: str, *, run_dir: Path | None = None) -> Path:
    """Resolve the per-run directory (creates nothing)."""
    if run_dir is not None:
        return run_dir
    return _DEFAULT_RUNS_ROOT / run_id


def spine_path_for_run(run_id: str, *, run_dir: Path | None = None) -> Path:
    """``<run_dir>/<run_id>.spine.jsonl`` durable ledger path."""
    return run_dir_for(run_id, run_dir=run_dir) / spine_filename_for_run(run_id)


def exceptions_path_for_run(run_id: str, *, run_dir: Path | None = None) -> Path:
    """``<run_dir>/<run_id>.exceptions.jsonl`` grep-friendly index path."""
    return run_dir_for(run_id, run_dir=run_dir) / exceptions_filename_for_run(run_id)


__all__ = [
    "exceptions_path_for_run",
    "run_dir_for",
    "run_id_from_event_id",
    "spine_path_for_run",
]
