"""Run activity feed — a pure fold over the run ledger.

One row per run. Rows are recomputed from ``traces/runs/<run_id>/`` on read, so
the feed writes nothing and cannot drift from the facts it describes. ADR-0167
D11 fixes the spine ledger as the only source of truth and every materialized
view as rebuildable; this module follows that rule instead of keeping a second
mutable store beside it.

Two read paths, chosen by what the run still needs. A terminated run has
materialized ``journal.json``, a few kilobytes holding everything the row needs.
A live run has no journal yet, so its spine is folded instead. The split is not
an optimization bolted on later: spine ledgers in this tree reach gigabytes when
a run runs away, and only the live path has to touch one.

The memo is a read cache keyed on artifact identity. Dropping it costs a re-fold
and nothing else, which is what separates it from a source of truth.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)
from lca.infrastructure.persistence.run_paths import default_runs_root

DEFAULT_RUNS_ROOT = Path("traces/runs")
DEFAULT_LIMIT = 50

# Safety valve for the live path only. A healthy in-flight run stays far under
# this; a runaway ledger would otherwise stall the status endpoint for tens of
# seconds. Tool counts past the budget are not reported, which is why the bound
# is high enough that reaching it is already an incident.
LIVE_SPINE_BYTE_BUDGET = 64 * 1024 * 1024

# ``kernel.run.start`` opens the ledger, so recovering it never needs more than
# the first few records.
_SPINE_HEAD_BUDGET = 256 * 1024

# The harness owns this run-id naming convention. owner: activity feed.
# The test suite now writes its runs to ``LCA_RUNS_ROOT`` (see
# ``run_paths.default_runs_root``), so this exclusion only matters for harness
# runs that predate that isolation.
_HARNESS_RUN_PREFIXES = ("run_test_", "run_e2e_smoke_")

# Substring prefilter before json.loads. llm.stream.token and
# phase_graph.node.end dominate the ledger and can carry the entire
# model-visible prompt, so parsing every line costs seconds per megabyte while
# the matching lines cost microseconds.
_WANTED_MARKERS = (
    b'"kernel.run.start"',
    b'"kernel.run.stop"',
    b'"phase.think.fold"',
    b'"step.tool_call.record"',
)

_FAILURE_OUTCOMES = frozenset({"failure", "failed", "error"})
_CANCEL_OUTCOMES = frozenset({"cancelled", "canceled", "stopped", "interrupted"})

_TERMINATED_MARKER = "manifest.json"
_JOURNAL_NAME = "journal.json"


def _category_for(tool_name: str) -> ActivityCategory:
    lowered = tool_name.lower()
    if "shell" in lowered or "exec" in lowered or "command" in lowered:
        return ActivityCategory.COMMAND
    if "subagent" in lowered:
        return ActivityCategory.SUBAGENT
    if "browser" in lowered:
        return ActivityCategory.BROWSER
    if "cron" in lowered:
        return ActivityCategory.CRON
    return ActivityCategory.TOOL


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _iso(moment: datetime | None) -> str:
    return moment.isoformat() if moment is not None else ""


def _status_for(outcome: str, *, terminated: bool) -> ActivityStatus:
    if not terminated:
        return ActivityStatus.RUNNING
    lowered = outcome.lower()
    if lowered in _FAILURE_OUTCOMES:
        return ActivityStatus.FAILED
    if lowered in _CANCEL_OUTCOMES:
        return ActivityStatus.CANCELLED
    return ActivityStatus.COMPLETED


def _clean_objective(raw: str) -> str:
    """Trim injected scaffolding off an objective.

    The perceive phase appends system context to the user's text before it
    reaches the fold, so the raw objective can carry an HTML comment block that
    is not what the user typed.
    """
    return " ".join(raw.split("<!--", 1)[0].split())


@dataclass(frozen=True)
class _RunFacts:
    """What the feed reads out of one run."""

    run_id: str
    objective: str
    outcome: str
    started_at: datetime | None
    closed_at: datetime | None
    tool_calls: tuple[tuple[str, dict[str, Any]], ...]
    terminated: bool


def _tool_call(name: str, arguments: Any) -> tuple[str, dict[str, Any]] | None:
    if not name:
        return None
    return (name, arguments if isinstance(arguments, dict) else {})


def _fold_journal(run_dir: Path, journal: Path) -> _RunFacts | None:
    try:
        document = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(document, dict):
        return None

    raw_metadata = document.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}

    tool_calls: list[tuple[str, dict[str, Any]]] = []
    for step in document.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            pair = _tool_call(
                str(call.get("name") or call.get("tool_name") or ""),
                call.get("arguments"),
            )
            if pair is not None:
                tool_calls.append(pair)

    return _RunFacts(
        run_id=run_dir.name,
        objective=str(metadata.get("objective") or ""),
        outcome=str(metadata.get("outcome") or ""),
        started_at=_parse_ts(metadata.get("started_at")),
        closed_at=_parse_ts(metadata.get("closed_at")),
        tool_calls=tuple(tool_calls),
        terminated=True,
    )


def _fold_spine(run_dir: Path, spine: Path, *, terminated: bool = False) -> _RunFacts | None:
    objective = ""
    outcome = ""
    started_at: datetime | None = None
    closed_at: datetime | None = None
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    saw_any = False

    try:
        handle = spine.open("rb")
    except OSError:
        return None

    with handle:
        budget = LIVE_SPINE_BYTE_BUDGET
        for raw in handle:
            budget -= len(raw)
            if budget < 0:
                break
            if not any(marker in raw for marker in _WANTED_MARKERS):
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            saw_any = True
            point = record.get("execution_point")
            raw_payload = record.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            moment = _parse_ts(record.get("ts"))

            if point == "kernel.run.start":
                started_at = moment
            elif point == "kernel.run.stop":
                closed_at = moment
                outcome = str(payload.get("outcome") or payload.get("status") or "completed")
            elif point == "phase.think.fold" and not objective:
                objective = str(payload.get("objective") or "")
            elif point == "step.tool_call.record":
                pair = _tool_call(
                    str(payload.get("tool_name") or ""),
                    payload.get("arguments"),
                )
                if pair is not None:
                    tool_calls.append(pair)

    if not saw_any:
        return None
    return _RunFacts(
        run_id=run_dir.name,
        objective=objective,
        outcome=outcome,
        started_at=started_at,
        closed_at=closed_at,
        tool_calls=tuple(tool_calls),
        terminated=terminated or bool(outcome),
    )


def _spine_start_time(run_dir: Path) -> datetime | None:
    """Recover a start time the journal does not carry.

    Runs that fail before their first step materialize a journal whose
    ``started_at`` is still 0.0, while the ledger's opening ``kernel.run.start``
    record holds the real moment. Reading it back keeps the row ordered by when
    the run actually began.
    """
    spines = sorted(run_dir.glob("*.spine.jsonl"))
    if not spines:
        return None
    try:
        handle = spines[0].open("rb")
    except OSError:
        return None
    with handle:
        budget = _SPINE_HEAD_BUDGET
        for raw in handle:
            budget -= len(raw)
            if budget < 0:
                return None
            if b'"kernel.run.start"' not in raw:
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                return None
            return _parse_ts(record.get("ts")) if isinstance(record, dict) else None
    return None


def _summarize_tools(tool_calls: tuple[tuple[str, dict[str, Any]], ...]) -> str:
    if not tool_calls:
        return "未调用工具，直接回复"
    names = [name for name, _ in tool_calls]
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    summary = f"调用 {len(names)} 个工具：{'、'.join(unique[:3])}"
    if len(unique) > 3:
        summary += " 等"
    return summary


def _row_from_facts(facts: _RunFacts) -> ActivityItem:
    first_tool, first_args = facts.tool_calls[0] if facts.tool_calls else ("", {})
    icon = ActivityIntentNamer.name(first_tool, first_args)[2] if first_tool else "chat"
    status = _status_for(facts.outcome, terminated=facts.terminated)

    current_step: str | None = None
    if status is ActivityStatus.RUNNING:
        last_tool, last_args = facts.tool_calls[-1] if facts.tool_calls else ("", {})
        current_step = (
            ActivityIntentNamer.name(last_tool, last_args)[0] if last_tool else "智能体思考并回复中"
        )

    duration_ms: int | None = None
    if facts.started_at is not None and facts.closed_at is not None:
        duration_ms = max(0, int((facts.closed_at - facts.started_at).total_seconds() * 1000))

    title = _clean_objective(facts.objective) or first_tool or f"运行 {facts.run_id[-6:]}"
    if len(title) > 60:
        title = title[:60] + "…"

    return ActivityItem(
        id=facts.run_id,
        run_id=facts.run_id,
        # Run artifacts carry no assistant binding, so the feed cannot scope
        # rows per assistant. An empty value states that plainly; inventing
        # "default" would make an unscoped feed look scoped. Persisting the
        # binding on the run is what lets the snapshot filter again.
        assistant_id="",
        category=_category_for(first_tool),
        title=title,
        summary=_summarize_tools(facts.tool_calls),
        status=status,
        start_time=_iso(facts.started_at),
        end_time=_iso(facts.closed_at) or None,
        duration_ms=duration_ms,
        icon=icon,
        tool_name=first_tool,
        current_step=current_step,
    )


@dataclass(frozen=True)
class _MemoEntry:
    stamp: tuple[str, float, int]
    item: ActivityItem | None


class ActivityFeed:
    """Fold the run ledger into run-level activity rows on read."""

    def __init__(
        self,
        runs_root: Path | str | None = None,
        *,
        limit: int = DEFAULT_LIMIT,
        scan_limit: int = 400,
    ) -> None:
        self._runs_root = Path(runs_root) if runs_root is not None else default_runs_root()
        self._limit = limit
        self._scan_limit = scan_limit
        self._memo: dict[str, _MemoEntry] = {}

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def list_activities(self, *, live_run_ids: Collection[str] = ()) -> list[ActivityItem]:
        """Return the newest runs as activity rows, most recent first.

        ``live_run_ids`` is the caller's authority on which runs are still
        executing. A run qualifies when it terminated, meaning its materialized
        views landed, or when the caller says it is live. Unterminated runs
        nobody is executing are abandoned and stay out of the feed instead of
        showing as running forever.
        """
        live = frozenset(live_run_ids)
        rows: list[ActivityItem] = []
        for run_dir, terminated in self._candidate_run_dirs(live):
            item = self._fold(run_dir, terminated=terminated)
            if item is not None:
                rows.append(item)
        rows.sort(key=lambda row: row.start_time, reverse=True)
        return rows[: self._limit]

    def invalidate(self) -> None:
        self._memo.clear()

    def _candidate_run_dirs(self, live: frozenset[str]) -> list[tuple[Path, bool]]:
        if not self._runs_root.is_dir():
            return []
        stamped: list[tuple[float, Path]] = []
        for run_dir in self._runs_root.iterdir():
            name = run_dir.name
            if not name.startswith("run_") or name.startswith(_HARNESS_RUN_PREFIXES):
                continue
            try:
                stamped.append((run_dir.stat().st_mtime, run_dir))
            except OSError:
                continue
        stamped.sort(key=lambda pair: pair[0], reverse=True)

        candidates: list[tuple[Path, bool]] = []
        for _, run_dir in stamped[: self._scan_limit]:
            terminated = (run_dir / _TERMINATED_MARKER).is_file()
            if terminated or run_dir.name in live:
                candidates.append((run_dir, terminated))
        return candidates

    def _fold(self, run_dir: Path, *, terminated: bool) -> ActivityItem | None:
        journal = run_dir / _JOURNAL_NAME
        from_journal = terminated and journal.is_file()
        if from_journal:
            source = journal
        else:
            spines = sorted(run_dir.glob("*.spine.jsonl"))
            if not spines:
                return None
            source = spines[0]

        try:
            info = source.stat()
        except OSError:
            return None
        stamp = (source.name, info.st_mtime, info.st_size)

        cached = self._memo.get(run_dir.name)
        if cached is not None and cached.stamp == stamp:
            return cached.item

        facts = (
            _fold_journal(run_dir, source)
            if from_journal
            else _fold_spine(run_dir, source, terminated=terminated)
        )
        if facts is None and from_journal:
            spines = sorted(run_dir.glob("*.spine.jsonl"))
            facts = _fold_spine(run_dir, spines[0], terminated=terminated) if spines else None
        if facts is not None and facts.started_at is None:
            facts = replace(facts, started_at=_spine_start_time(run_dir))

        item = _row_from_facts(facts) if facts is not None else None
        self._memo[run_dir.name] = _MemoEntry(stamp=stamp, item=item)
        return item


_FEED: ActivityFeed | None = None


def get_activity_feed() -> ActivityFeed:
    """Return the process-wide feed. Construction performs no I/O."""
    global _FEED
    if _FEED is None:
        _FEED = ActivityFeed()
    return _FEED


__all__ = (
    "DEFAULT_LIMIT",
    "DEFAULT_RUNS_ROOT",
    "LIVE_SPINE_BYTE_BUDGET",
    "ActivityFeed",
    "get_activity_feed",
)
