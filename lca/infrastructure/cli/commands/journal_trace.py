"""Journal trace — print one event per line, optionally with I17 source columns.

Task 9.3: ``lca-ops journal trace <run_id> [--locals] [--source]`` reads
the append-only ``events.jsonl`` written by the spine ``FileSink`` and
prints a human-readable table. The default view shows ``seq / execution
point / channel / outcome / when``. With ``--source`` two extra columns
appear (``source_location`` file:line and the function name). With
``--locals`` (which implies ``--source``) two more columns are added:
the first ``call_frames`` entry beyond ``source_location`` and a compact
``locals_snapshot.pre_call`` rendering.

The CLI sits under ``journal`` to keep the LCA Spine concerns grouped;
the older ``lca-ops trace`` command remains for legacy ``journal.jsonl``
replay (via ``TraceInspectorToolAdapter``). Both surfaces are read-only.

I17 contract
------------
Every ``*.start`` event MUST carry ``source_location`` /
``call_frames`` / ``locals_snapshot``. The CLI does NOT enforce this;
that lives in ``EmitPipeline.emit``. A misconfigured pipeline produces
``"-"`` in the source columns and the operator sees the gap instead of
a stack trace.

Not in scope
------------
- The CLI does NOT fall back to ``journal.jsonl``. Spine events and the
  legacy ``journal.jsonl`` are two separate streams; mixing them would
  hide I17 violations. If ``events.jsonl`` is missing the CLI emits a
  short error and ``typer.Exit(1)``.
- The CLI does NOT resolve offloaded sidecars (>4 KB rows live in
  ``<event_hash>.json``). Out-of-scope here; future PR can wire a
  sidecar reader.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI default traces root

# Maximum number of locals we render per row. Caps the width of the
# ``--locals`` column so a long snapshot does not break table layout.
_LOCAL_RENDER_LIMIT = 4

# Maximum number of bytes we serialise per locals value. Mirrors the
# SourceAttacher 4 KB ceiling for the snapshot itself.
_LOCAL_VALUE_LIMIT = 64


@dataclass(frozen=True, slots=True)
class TraceRow:
    """One row in the ``journal trace`` table.

    ``source_file`` / ``source_function`` are empty strings when the
    event lacks ``source_location``; the renderer maps them to ``"-"``.
    """

    seq: int
    execution_point: str
    channel: str
    outcome: str
    when: str
    source_file: str
    source_line: int | None
    source_function: str
    next_frame: str
    locals_render: str


def _iter_events(events_path: Path) -> Iterator[dict[str, Any]]:
    """Yield one decoded record per line of ``events.jsonl``.

    Blank lines are silently skipped (no count). JSON decode failures
    yield a sentinel ``{"__decode_error__": True}`` so the caller can
    surface them in the ``skipped`` counter; offloaded placeholders
    flow through unchanged so the operator sees they exist.
    """
    with events_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                yield {"__decode_error__": True}


def _extract_source_location(payload: dict[str, Any]) -> tuple[str, int | None, str]:
    """Return ``(file, line, function)`` from the event payload.

    Accepts both the dataclass-shape ``SourceLocation`` and a plain
    ``dict`` so the CLI works regardless of the producer's serialiser.
    Missing keys map to ``""`` / ``None`` / ``""``; the renderer marks
    them with ``"-"``.
    """
    location = payload.get("source_location")
    if not isinstance(location, dict):
        return ("", None, "")
    file_value = location.get("file", "")
    line_value = location.get("line")
    function_value = location.get("function", "")
    if not isinstance(file_value, str):
        file_value = ""
    if not isinstance(function_value, str):
        function_value = ""
    if not isinstance(line_value, int):
        line_value = None
    return (file_value, line_value, function_value)


def _extract_next_frame(payload: dict[str, Any]) -> str:
    """Return ``"file:line (function)"`` for the next ``call_frames`` entry.

    The first ``call_frames`` entry is by convention the immediate
    caller of ``source_location`` (frames are outermost-first). When
    ``call_frames`` is empty or missing we return ``""`` so the
    renderer prints ``"-"``.
    """
    frames = payload.get("call_frames")
    if not isinstance(frames, list) or not frames:
        return ""
    first = frames[0]
    if not isinstance(first, dict):
        return ""
    file_value = str(first.get("file", ""))
    line_value = first.get("line")
    function_value = str(first.get("function", ""))
    if not file_value:
        return ""
    if isinstance(line_value, int):
        return f"{file_value}:{line_value} ({function_value})"
    return f"{file_value} ({function_value})"


def _render_locals(payload: dict[str, Any]) -> str:
    """Return a one-line rendering of ``locals_snapshot.pre_call``.

    Walks ``locals`` / ``ctx`` envelopes (the SourceAttacher envelope
    shape) and concatenates up to ``_LOCAL_RENDER_LIMIT`` entries,
    trimming each value to ``_LOCAL_VALUE_LIMIT`` bytes. Returns ``""``
    when the snapshot is empty so the renderer prints ``"-"``.
    """
    snapshot = payload.get("locals_snapshot")
    if not isinstance(snapshot, dict):
        return ""
    pre_call = snapshot.get("pre_call")
    if not isinstance(pre_call, dict):
        return ""
    parts: list[str] = []
    for envelope, entries in pre_call.items():
        if not isinstance(entries, dict) or not entries:
            continue
        for name, value in entries.items():
            if len(parts) >= _LOCAL_RENDER_LIMIT:
                parts.append("…")
                return " | ".join(parts)
            text = str(value)
            if len(text) > _LOCAL_VALUE_LIMIT:
                text = text[: _LOCAL_VALUE_LIMIT - 1] + "…"
            parts.append(f"{envelope}.{name}={text}")
    return " | ".join(parts)


def _event_to_row(seq: int, event: dict[str, Any]) -> TraceRow:
    """Project one ``events.jsonl`` line into a :class:`TraceRow`."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    file_value, line_value, function_value = _extract_source_location(payload)
    next_frame = _extract_next_frame(payload)
    locals_render = _render_locals(payload)
    return TraceRow(
        seq=seq,
        execution_point=str(event.get("execution_point", "?")),
        channel=str(event.get("channel", "?")),
        outcome=str(event.get("outcome") or ""),
        when=str(event.get("when", "")),
        source_file=file_value,
        source_line=line_value,
        source_function=function_value,
        next_frame=next_frame,
        locals_render=locals_render,
    )


def _format_source_column(row: TraceRow) -> str:
    """Render the ``source_location`` column as ``"file:line (fn)"`` or ``"-"``."""
    if not row.source_file:
        return "-"
    if row.source_line is None:
        return f"{row.source_file} ({row.source_function})"
    return f"{row.source_file}:{row.source_line} ({row.source_function})"


def _format_column(value: str, fallback: str = "-") -> str:
    """Return ``value`` when truthy, else ``fallback``. Used by frame / locals."""
    return value if value else fallback


def _row_iter_to_table(rows: Iterable[TraceRow], *, with_locals: bool) -> str:
    """Render rows as an aligned table.

    ``with_locals`` controls whether the extra columns are emitted. We
    always emit the same set of base columns (``seq / point / channel /
    outcome / when / source``); the ``--locals`` flag adds
    ``next_frame`` and ``locals``.
    """
    base_columns: list[tuple[str, str]] = [
        ("seq", "seq"),
        ("execution_point", "execution_point"),
        ("channel", "channel"),
        ("outcome", "outcome"),
        ("when", "when"),
        ("source", "source"),
    ]
    if with_locals:
        base_columns.extend(
            [
                ("next_frame", "next_frame"),
                ("locals", "locals"),
            ]
        )

    field_map = {
        "seq": lambda r: str(r.seq),
        "execution_point": lambda r: r.execution_point,
        "channel": lambda r: r.channel,
        "outcome": lambda r: r.outcome or "-",
        "when": lambda r: r.when,
        "source": _format_source_column,
        "next_frame": lambda r: _format_column(r.next_frame),
        "locals": lambda r: _format_column(r.locals_render),
    }

    materialised = list(rows)
    widths: dict[str, int] = {}
    for col, header in base_columns:
        widths[col] = max(
            len(header),
            max((len(field_map[col](r)) for r in materialised), default=0),
        )

    lines: list[str] = []
    header_line = "  ".join(f"{header:<{widths[col]}}" for col, header in base_columns)
    lines.append(header_line)
    lines.append("  ".join("-" * widths[col] for col, _ in base_columns))
    for row in materialised:
        lines.append("  ".join(f"{field_map[col](row):<{widths[col]}}" for col, _ in base_columns))
    return "\n".join(lines)


def _resolve_events_path(traces_root: Path, run_id: str) -> Path:
    """Resolve ``<run_dir>/events.jsonl`` or surface a friendly error."""
    locator = FilesystemRunLocator(traces_root)
    run_dir = locator.run_dir(run_id)
    if not run_dir.exists():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        print("  hint: 检查 --traces-root 是否正确,run_id 是否存在", file=sys.stderr)
        raise SystemExit(1)
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        print(
            f"events.jsonl not found: {events_path}\n"
            f"  hint: spine FileSink 尚未写入 events,或 run {run_id} 不在 PR-9 之后",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return events_path


def register(app: typer.Typer) -> None:
    """Register the ``trace`` command under the ``journal`` group."""

    @app.command(name="trace")
    def trace_cmd(
        run_id: str = typer.Argument(..., help="run_id (e.g. run_c38532761cfb)"),
        with_locals: bool = typer.Option(
            False, "--locals", help="在表格里追加 next_frame + locals_snapshot 列"
        ),
        with_source: bool = typer.Option(
            False, "--source", help="在表格里追加 source_location 列(默认开)"
        ),
        json_output: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
        limit: int = typer.Option(0, "--limit", "-n", help="只输出前 N 行(0 = 全部)"),
    ) -> None:
        """检查一个 run 的 spine ``events.jsonl``(只读,PR-9 I17 起生效)。

        默认列:``seq / execution_point / channel / outcome / when / source``。

        --source / --locals 都开时,额外追加 ``next_frame`` 和
        ``locals_snapshot.pre_call`` 列。``--locals`` 隐含开启
        ``--source`` —— locals 列依赖 source_location 才能定位
        Frame。
        """
        # ``--locals`` implies ``--source`` so the table is consistent:
        # locals without source_location is ambiguous.
        if with_locals:
            with_source = True

        events_path = _resolve_events_path(traces_root, run_id)
        rows: list[TraceRow] = []
        skipped = 0
        total = 0
        for event in _iter_events(events_path):
            total += 1
            if event.get("__decode_error__"):
                skipped += 1
                if limit > 0 and len(rows) >= limit:
                    break
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                skipped += 1
                if limit > 0 and len(rows) >= limit:
                    break
                continue
            seq = int(event.get("sequence", 0) or 0)
            rows.append(_event_to_row(seq, event))
            if limit > 0 and len(rows) >= limit:
                break

        if json_output:
            payload_rows = [
                {
                    "seq": r.seq,
                    "execution_point": r.execution_point,
                    "channel": r.channel,
                    "outcome": r.outcome,
                    "when": r.when,
                    "source_location": (
                        {
                            "file": r.source_file,
                            "line": r.source_line,
                            "function": r.source_function,
                        }
                        if r.source_file
                        else None
                    ),
                    "next_frame": r.next_frame or None,
                    "locals_snapshot": r.locals_render or None,
                }
                for r in rows
            ]
            report = {
                "schema": "lca.journal_trace/1",
                "run_id": run_id,
                "events_path": str(events_path),
                "total": total,
                "rendered": len(rows),
                "skipped": skipped,
                "with_locals": with_locals,
                "with_source": with_source,
                "rows": payload_rows,
            }
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            sys.stdout.write("\n")
            return

        table = _row_iter_to_table(rows, with_locals=with_locals)
        sys.stdout.write(table)
        sys.stdout.write("\n")
        sys.stdout.write(
            f"\n── trace done: {len(rows)}/{total} events rendered, "
            f"{skipped} skipped (events.jsonl={events_path}) ──\n"
        )


__all__ = ["register"]
