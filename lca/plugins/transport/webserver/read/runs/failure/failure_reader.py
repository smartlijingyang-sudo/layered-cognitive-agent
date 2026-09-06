"""Read-side failure projection for transport (ADR-0195 observe plane)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_TRACES_ROOT = Path("traces") / "runs"


def _run_dir(run_id: str, *, traces_root: Path = _DEFAULT_TRACES_ROOT) -> Path:
    return traces_root / run_id


def load_exception_records(
    run_id: str,
    *,
    traces_root: Path = _DEFAULT_TRACES_ROOT,
) -> list[dict[str, Any]]:
    """Load ``exception.caught`` payloads from ``*.exceptions.jsonl`` or spine fallback."""
    run_path = _run_dir(run_id, traces_root=traces_root)
    exceptions_path = run_path / f"{run_id}.exceptions.jsonl"
    records: list[dict[str, Any]] = []
    if exceptions_path.is_file():
        for line in exceptions_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
            if isinstance(payload, dict):
                records.append(payload)
        return records

    spine_path = run_path / f"{run_id}.spine.jsonl"
    if not spine_path.is_file():
        return []
    for line in spine_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("execution_point") != "exception.caught":
            continue
        payload = row.get("payload")
        if isinstance(payload, dict):
            records.append(payload)
    return records


def failure_summary_for_run(
    run_id: str,
    *,
    user_error: str = "",
    traces_root: Path = _DEFAULT_TRACES_ROOT,
) -> dict[str, Any]:
    """Operator-facing failure DTO: sanitized user message + exception index."""
    records = load_exception_records(run_id, traces_root=traces_root)
    latest = records[-1] if records else {}
    return {
        "run_id": run_id,
        "user_message": user_error,
        "exception_class": latest.get("exception_class") or latest.get("exc_type") or "",
        "exception_message": latest.get("exception_message") or latest.get("message") or "",
        "err_kind": latest.get("err_kind") or "",
        "boundary": latest.get("boundary") or "",
        "exception_count": len(records),
        "has_traceback": bool(latest.get("traceback_text")),
    }


__all__ = ["failure_summary_for_run", "load_exception_records"]
