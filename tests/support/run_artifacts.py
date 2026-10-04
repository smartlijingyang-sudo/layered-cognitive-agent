"""Shared run-artifact fixture builders.

Three status-screen test modules used to hand-roll identical writers for
``manifest.json``, ``journal.json`` and spine ledgers. These builders are the
union of those local copies and reproduce the real artifact shapes:

* ``manifest.json`` — ``lca.run_manifest/1`` with the run-level keys.
* ``journal.json`` — ``lca.journal/3.1`` with the full metadata block and
  per-step ``tool_calls``/``tool_results``.
* spine ledgers — every record keeps the full envelope
  (``category``/``causation_id``/``channel``/``event_hash``/``event_id``/
  ``execution_point``/``payload``/``prev_event_hash``/``trace_id``/``ts``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

OBJECTIVE = "把 Drive 里的合同汇总一下"
TRACE_ID = "trace_f564881799d0"

_PLAN_REF = "sha256:41a03bd9ce232ff6"
_DEFAULT_STARTED_AT = 1791041881.0
_DEFAULT_CLOSED_AT = 1791041903.0
_DEFAULT_START_TS = "2026-10-03T15:42:29Z"

ToolCall = tuple[str, dict[str, Any]]
ToolCalls = Sequence[Sequence[ToolCall]]


def run_dir(runs_root: Path, run_id: str) -> Path:
    """Create and return the run directory under ``runs_root``."""
    directory = runs_root / run_id
    directory.mkdir(parents=True)
    return directory


def write_manifest(
    run_dir_path: Path,
    run_id: str | None = None,
    *,
    session_status: str = "completed",
) -> None:
    """Write ``manifest.json`` marking a run as terminated.

    ``run_id`` defaults to ``run_dir_path.name`` so callers that only know the
    directory (the activity-feed tests) keep passing a single argument.
    """
    (run_dir_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "lca.run_manifest/1",
                "run_id": run_id or run_dir_path.name,
                "plan_ref": _PLAN_REF,
                "session_error": "",
                "session_status": session_status,
                "terminal_event_seq": 0,
                "ledger_high_watermark": 0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_journal(
    run_dir_path: Path,
    run_id: str | None = None,
    *,
    objective: str,
    outcome: str,
    started_at: float,
    closed_at: float | None,
    steps: ToolCalls = (),
    tool_calls: Sequence[ToolCall] | None = None,
) -> None:
    """Write ``journal.json`` for a terminated run.

    ``steps`` and ``tool_calls`` carry the same tool-call facts in the two
    shapes the callers used: ``steps`` is per-step (a sequence of steps, each
    holding one or more ``(name, arguments)`` calls) while ``tool_calls`` is a
    flat sequence of ``(name, arguments)`` pairs with one call per step. A
    running invocation counter keeps ``invocation_id`` unique even when one step
    carries several tool calls.
    """
    if tool_calls is not None:
        per_step: ToolCalls = tuple((call,) for call in tool_calls)
    else:
        per_step = steps
    invocation = 0
    journal_steps: list[dict[str, Any]] = []
    for index, calls in enumerate(per_step, start=1):
        recorded_calls: list[dict[str, Any]] = []
        for name, arguments in calls:
            invocation += 1
            recorded_calls.append(
                {
                    "invocation_id": f"toolu_{invocation:04d}",
                    "name": name,
                    "arguments": arguments,
                }
            )
        journal_steps.append(
            {
                "step_index": index,
                "entered_at": started_at,
                "tool_calls": recorded_calls,
                "tool_results": [],
            }
        )
    (run_dir_path / "journal.json").write_text(
        json.dumps(
            {
                "schema": "lca.journal/3.1",
                "run_id": run_id or run_dir_path.name,
                "metadata": {
                    "agent_role": "solo",
                    "strategy_key": "solo",
                    "plan_ref": _PLAN_REF,
                    "objective": objective,
                    "attachments": [],
                    "outcome": outcome,
                    "started_at": started_at,
                    "closed_at": closed_at,
                    "total_steps": len(journal_steps),
                    "extra": {},
                },
                "steps": journal_steps,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_terminated_run(
    runs_root: Path,
    run_id: str,
    *,
    objective: str = OBJECTIVE,
    outcome: str = "completed",
    started_at: float = _DEFAULT_STARTED_AT,
    closed_at: float | None = _DEFAULT_CLOSED_AT,
    steps: ToolCalls = (),
    tool_calls: Sequence[ToolCall] | None = None,
) -> Path:
    """Create a terminated run (manifest + journal) and return its directory."""
    directory = run_dir(runs_root, run_id)
    write_manifest(directory, run_id, session_status=outcome)
    write_journal(
        directory,
        run_id,
        objective=objective,
        outcome=outcome,
        started_at=started_at,
        closed_at=closed_at,
        steps=steps,
        tool_calls=tool_calls,
    )
    return directory


def spine_record(
    run_id: str,
    *,
    seq: int,
    execution_point: str,
    payload: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    """Build one spine ledger record with the full envelope."""
    return {
        "category": f"spine.{execution_point}",
        "causation_id": None,
        "channel": "fact",
        "event_hash": None,
        "event_id": f"{run_id}:{seq}",
        "execution_point": execution_point,
        "payload": payload,
        "prev_event_hash": None,
        "trace_id": None,
        "ts": ts,
    }


def spine_line(
    run_id: str,
    seq: int,
    execution_point: str,
    payload: dict[str, Any],
    ts: str,
) -> str:
    """Serialize one spine record as a JSON line (no trailing newline)."""
    return json.dumps(
        spine_record(
            run_id,
            seq=seq,
            execution_point=execution_point,
            payload=payload,
            ts=ts,
        ),
        ensure_ascii=False,
    )


def _tool_payload(run_id: str, seq: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "arguments": arguments,
        "arguments_summary": ", ".join(f"{k}={v!r}" for k, v in arguments.items()),
        "invocation_id": f"toolu_{seq:04d}",
        "run_id": run_id,
        "step": seq,
        "tool_name": name,
    }


def tool_line(run_id: str, seq: int, name: str, arguments: dict[str, Any], ts: str) -> str:
    """Serialize a ``step.tool_call.record`` spine line."""
    return spine_line(
        run_id,
        seq,
        "step.tool_call.record",
        _tool_payload(run_id, seq, name, arguments),
        ts,
    )


def write_spine(
    run_dir_path: Path,
    run_id: str,
    *,
    started_ts: str,
    objective: str = "",
    tool_calls: Sequence[ToolCall] = (),
    stop_outcome: str | None = None,
    stop_ts: str | None = None,
) -> None:
    """Write a spine ledger into an existing run directory.

    The ledger opens with ``kernel.run.start`` and, when an objective is known,
    a ``phase.think.fold``; tool calls are recorded as
    ``step.tool_call.record`` and an optional ``kernel.run.stop`` closes the run.
    """
    records: list[dict[str, Any]] = [
        spine_record(
            run_id,
            seq=1,
            execution_point="kernel.run.start",
            payload={"run_id": run_id, "trace_id": f"trace_{run_id}"},
            ts=started_ts,
        )
    ]
    seq = 2
    if objective:
        records.append(
            spine_record(
                run_id,
                seq=seq,
                execution_point="phase.think.fold",
                payload={
                    "incarnation": 1,
                    "objective": objective,
                    "objective_kind": "user_text",
                    "phase": "think",
                    "summary": "started",
                },
                ts=started_ts,
            )
        )
        seq += 1
    for name, arguments in tool_calls:
        records.append(
            spine_record(
                run_id,
                seq=seq,
                execution_point="step.tool_call.record",
                payload=_tool_payload(run_id, seq, name, arguments),
                ts=started_ts,
            )
        )
        seq += 1
    if stop_outcome is not None:
        records.append(
            spine_record(
                run_id,
                seq=seq,
                execution_point="kernel.run.stop",
                payload={"outcome": stop_outcome, "run_id": run_id, "trace_id": f"trace_{run_id}"},
                ts=stop_ts or started_ts,
            )
        )
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    (run_dir_path / f"{run_id}.spine.jsonl").write_text(lines, encoding="utf-8")


def write_live_run(
    runs_root: Path,
    run_id: str,
    *,
    objective: str = OBJECTIVE,
    started_ts: str = _DEFAULT_START_TS,
    tool_calls: Sequence[ToolCall] = (),
    stop_outcome: str | None = None,
    stop_ts: str | None = None,
    start_ts: str | None = None,
) -> Path:
    """Create a live run (spine ledger, no manifest) and return its spine path.

    ``started_ts`` and ``start_ts`` alias the same opening timestamp; the
    activity-feed caller used ``start_ts``.
    """
    ts = start_ts if start_ts is not None else started_ts
    directory = run_dir(runs_root, run_id)
    write_spine(
        directory,
        run_id,
        started_ts=ts,
        objective=objective,
        tool_calls=tool_calls,
        stop_outcome=stop_outcome,
        stop_ts=stop_ts,
    )
    return directory / f"{run_id}.spine.jsonl"


__all__ = (
    "OBJECTIVE",
    "TRACE_ID",
    "ToolCall",
    "ToolCalls",
    "run_dir",
    "spine_line",
    "spine_record",
    "tool_line",
    "write_journal",
    "write_live_run",
    "write_manifest",
    "write_spine",
    "write_terminated_run",
)
