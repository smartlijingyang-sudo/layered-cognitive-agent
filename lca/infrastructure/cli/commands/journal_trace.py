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
import os
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI default traces root

# Cap on the absolute-time cell so a long run does not push alignment out.
_TIME_CELL_WIDTH = 9

# Cap on the relative-time cell ("Δ+…ms"); kept short on purpose.
_DELTA_WIDTH = 8

# Cap on the longest "extra" detail payload before we elide with ``…``.
_DETAIL_VALUE_LIMIT = 240

# Cap on the prompt_preview blob that ``--human`` dumps inline.
_PROMPT_PREVIEW_LIMIT = 800

# Fold thresholds: a stream of consecutive same-EP events longer than this
# collapses into one summary line. Keeps token storms readable without
# losing any payload text.
_TOKEN_FOLD_MIN = 3
_REDUCER_FOLD_MIN = 3

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


# ── human view (Phase 1) ───────────────────────────────────────────────
#
# The view layer below translates the spine ``events.jsonl`` SSOT into a
# tree-shaped timeline that surfaces every node's own payload text. The
# SSOT schema (``EventRecord``) is intentionally untouched — see
# ADR-0167 + ADR-0165 I12 for the close-set contract. This module is
# read-only and lives entirely in ``journal_trace.py`` so it can be
# unit-tested without booting a kernel.


def _event_kind(ep: str, payload: dict[str, Any], outcome: str | None) -> str:
    """Short verb phrase per EP — the "what happened" headline.

    Designed for the left column of each human row. Falls back to the
    raw EP name when the EP is unknown so no information is dropped
    on unknown EPs (the payload detail is still printed verbatim
    below the headline).
    """
    if ep == "kernel.run.start":
        return "kernel.run.start"
    if ep == "kernel.run.stop":
        return f"kernel.run.stop  outcome={outcome or '-'}"
    if ep == "kernel.run.cancelled":
        return "kernel.run.cancelled"
    if ep == "agent_loop.iteration.start":
        return (
            f"agent_loop.iteration.start  role={payload.get('role', '?')}"
            f"  kind={payload.get('iteration_kind', '?')}"
        )
    if ep == "agent_loop.iteration.end":
        return f"agent_loop.iteration.end  kind={payload.get('iteration_kind', '?')}"
    if ep == "phase_graph.node.start":
        sig = payload.get("signature_fingerprint", "")
        return f"phase_graph.node started  span={payload.get('span_id', '?')}  sig={sig}"
    if ep == "phase_graph.node.end":
        span = payload.get("span_id", "?")
        if (outcome or "").lower() != "success" or payload.get("error_type"):
            return f"phase_graph.node ended  span={span}  ✗"
        return f"phase_graph.node ended  span={span}"
    if ep == "transport.route.enter":
        return f"transport {payload.get('method', '?')} {payload.get('path', '?')} ▶"
    if ep == "transport.route.exit":
        return (
            f"transport {payload.get('method', '?')} {payload.get('path', '?')}"
            f" →{payload.get('status', '?')}"
        )
    if ep == "transport.sse.publish":
        return "transport.sse.publish"
    if ep == "llm.call.start":
        return f"llm.call.start  model={payload.get('model', '?')}"
    if ep == "llm.call.end":
        return (
            f"llm.call.end  latency={payload.get('latency_ms', '?')}ms"
            f"  prompt={payload.get('prompt_tokens', '?')} tok"
            f"  completion={payload.get('completion_tokens', '?')} tok"
        )
    if ep == "body.tool.execute.start":
        return (
            f"body.tool.execute.start  tool={payload.get('tool_name', '?')}"
            f"  attempt={payload.get('attempt', '?')}"
            f"  wrapper={payload.get('wrapper', '?')}"
        )
    if ep == "body.tool.execute.end":
        return (
            f"body.tool.execute.end  tool={payload.get('tool_name', '?')}"
            f"  latency={payload.get('latency_ms', '?')}ms"
        )
    if ep == "body.tool.retry":
        return "body.tool.retry"
    if ep == "body.sandbox.enter":
        return (
            f"body.sandbox.enter  invocation={payload.get('invocation_id', '?')[:16]}"
        )
    if ep == "body.sandbox.exit":
        return (
            f"body.sandbox.exit  invocation={payload.get('invocation_id', '?')[:16]}"
        )
    if ep == "phase.tool.call.start":
        return (
            f"phase.tool.call.start  tool={payload.get('tool_name', '?')}"
            f"  args={payload.get('arguments_summary', '')}"
        )
    if ep == "phase.tool.call.end":
        return (
            f"phase.tool.call.end  tool={payload.get('tool_name', '?')}"
            f"  ok={payload.get('ok')}  latency={payload.get('latency_ms', '?')}ms"
        )
    if ep == "phase.tool.denied":
        return f"phase.tool.denied  reason={payload.get('reason', '')}"
    if ep == "phase.perceive.fold":
        return f"phase.perceive.fold  objective={payload.get('objective', '?')}"
    if ep == "phase.think.fold":
        return "phase.think.fold"
    if ep == "phase.act.fold.start":
        return (
            f"phase.act.fold.start  tool={payload.get('tool_name', '?')}"
            f"  objective={payload.get('objective', '?')}"
        )
    if ep == "phase.act.fold.end":
        return f"phase.act.fold.end  outcome={payload.get('outcome', '?')}"
    if ep == "phase.reflect.fold":
        return "phase.reflect.fold"
    if ep == "phase.remember.fold":
        return "phase.remember.fold"
    if ep == "phase.stop.fold":
        return "phase.stop.fold"
    if ep == "brain.think.start":
        return f"brain.think.start  state={payload.get('state_id', '?')[:16]}"
    if ep == "brain.think.end":
        return f"brain.think.end  state={payload.get('state_id', '?')[:16]}"
    if ep == "reasoner.reason.start":
        return f"reasoner.reason.start  state={payload.get('state_id', '?')[:16]}"
    if ep == "reasoner.reason.end":
        return f"reasoner.reason.end  state={payload.get('state_id', '?')[:16]}"
    if ep == "critic.eval.start":
        return f"critic.eval.start  state={payload.get('state_id', '?')[:16]}"
    if ep == "critic.eval.end":
        return f"critic.eval.end  state={payload.get('state_id', '?')[:16]}"
    if ep == "synthesizer.merge":
        return f"synthesizer.merge  candidates={payload.get('candidate_count', '?')}"
    if ep == "skill_router.route":
        return "skill_router.route"
    if ep == "prompt_assembler.assemble.start":
        return (
            f"prompt_assembler.assemble.start  template={payload.get('template_id', '?')}"
        )
    if ep == "prompt_assembler.assemble.end":
        return (
            f"prompt_assembler.assemble.end  template={payload.get('template_id', '?')}"
            f"  sections={payload.get('section_count', '?')}"
        )
    if ep == "memory.read":
        return f"memory.read  state={payload.get('state_id', '?')[:16]}"
    if ep == "memory.write":
        return (
            f"memory.write  state={payload.get('state_id', '?')[:16]}"
            f"  layer={payload.get('layer', '?')}"
            f"  record={payload.get('record_id', '?')[:16]}"
        )
    if ep == "runtime.checkpoint.create":
        return "runtime.checkpoint.create"
    if ep == "runtime.resume.start":
        return "runtime.resume.start"
    if ep == "runtime.resume.end":
        return "runtime.resume.end"
    if ep == "runtime.reducer.apply":
        return (
            f"runtime.reducer.apply  method={payload.get('method', '?')}"
            f"  phase={payload.get('phase', '?')}"
        )
    if ep == "runtime.event_publisher.publish":
        return (
            f"runtime.event_publisher.publish  event_type={payload.get('event_type', '?')}"
        )
    if ep == "lifecycle.finally":
        return f"lifecycle.finally  boundary={payload.get('boundary', '?')}"
    if ep == "exception.caught":
        return f"✗ exception.caught  exc={payload.get('exc_type', '?')}"
    if ep == "exception.finally":
        return f"exception.finally  boundary={payload.get('boundary', '?')}"
    if ep == "writable.step.start":
        return "writable.step.start"
    if ep == "writable.step.end":
        return "writable.step.end"
    if ep == "writable.segment.start":
        return "writable.segment.start"
    if ep == "writable.segment.end":
        return "writable.segment.end"
    return ep


@dataclass(frozen=True, slots=True)
class _DetailBlock:
    """``_detail_lines`` return — lines plus a flag for the caller."""

    lines: tuple[str, ...]
    truncated: bool


def _detail_lines(ep: str, payload: dict[str, Any], *, max_lines: int) -> _DetailBlock:
    """Per-EP payload text the operator actually needs to understand the link.

    Returns verbatim text (no translation / no summarisation) for the
    payload fields that carry business content — ``delta_summary``,
    ``arguments_summary``, ``stdout_head``, ``files_created``,
    ``input_params``, ``output_schema``, ``preconditions``,
    ``exception_message``, ``traceback_snippet``, ``prompt_preview``.

    Unknown EPs fall back to ``key=value`` for every non-empty
    payload key so no information is silently dropped when a new EP
    appears before the table is updated.

    When the EP emits more lines than ``max_lines`` the leftover is
    counted and ``truncated=True`` so the caller can print a
    ``(+N more)`` hint without the caller having to re-render.
    """
    lines: list[str] = []
    truncated = False

    def _add(text: str) -> None:
        nonlocal truncated
        if len(lines) >= max_lines:
            truncated = True
            return
        lines.append(text)

    def _trim(s: str, limit: int = _DETAIL_VALUE_LIMIT) -> str:
        s = str(s)
        if len(s) <= limit:
            return s
        return s[: limit - 1] + "…"

    if ep == "phase_graph.node.start":
        params = payload.get("input_params")
        if isinstance(params, dict):
            _add(f"  ├ input_params = {_trim(json.dumps(params, ensure_ascii=False))}")
        elif params is not None:
            _add(f"  ├ input_params = {_trim(params)}")
        sig = payload.get("output_schema")
        if sig is not None:
            _add(f"  ├ output_schema = {_trim(json.dumps(sig, ensure_ascii=False))}")
        pre = payload.get("preconditions")
        if isinstance(pre, list) and pre:
            _add(f"  └ preconditions = [{', '.join(_trim(p) for p in pre)}]")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "phase_graph.node.end":
        if (payload.get("error_type") or payload.get("exception_message")):
            _add(f"  ✗ error_type={payload.get('error_type', '?')}")
            msg = payload.get("exception_message")
            if msg:
                _add("  ✗ exception_message:")
                for chunk in str(msg).splitlines() or [""]:
                    _add(f"    │ {_trim(chunk)}")
            tb = payload.get("traceback_snippet")
            if tb:
                _add("  ✗ traceback:")
                for chunk in str(tb).splitlines():
                    _add(f"    │ {_trim(chunk)}")
        else:
            rvf = payload.get("return_value_fingerprint")
            if rvf:
                _add(f"  └ return_value_fingerprint={_trim(rvf)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "phase.tool.call.end":
        ds = payload.get("delta_summary")
        if ds:
            _add(f"    delta_summary: {_trim(ds)}")
        sh = payload.get("stdout_head")
        if sh:
            _add(f"    stdout_head: {_trim(sh)}")
        fc = payload.get("files_created")
        if isinstance(fc, list) and fc:
            _add(f"    files_created: [{', '.join(str(x) for x in fc)}]")
        err = payload.get("error")
        if err:
            _add(f"    error: {_trim(err)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "phase.perceive.fold":
        sm = payload.get("summary")
        if sm:
            _add(f"    summary: {_trim(sm)}")
        obj = payload.get("objective")
        if obj:
            _add(f"    objective: {_trim(obj)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "phase.act.fold.end":
        err = payload.get("error")
        if err:
            _add(f"    error: {_trim(err)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "llm.call.start":
        pp = payload.get("prompt_preview")
        if pp:
            text = str(pp)
            if len(text) > _PROMPT_PREVIEW_LIMIT:
                text = text[: _PROMPT_PREVIEW_LIMIT - 1] + "…"
            _add("    prompt_preview:")
            for chunk in text.splitlines():
                _add(f"    │ {_trim(chunk, 200)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "exception.caught":
        msg = payload.get("message")
        if msg:
            _add("  ✗ message:")
            for chunk in str(msg).splitlines():
                _add(f"    │ {_trim(chunk)}")
        return _DetailBlock(tuple(lines), truncated)

    if ep == "phase.think.fold":
        obj = payload.get("objective")
        if obj:
            text = str(obj)
            if len(text) > _DETAIL_VALUE_LIMIT:
                text = text[: _DETAIL_VALUE_LIMIT - 1] + "…"
            _add(f"    objective: {text}")
        sm = payload.get("summary")
        if sm:
            _add(f"    summary: {_trim(sm)}")
        return _DetailBlock(tuple(lines), truncated)

    # Unknown EP / no specialised table — dump payload key=value verbatim
    # so no information is silently dropped.
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(value)
        _add(f"  {key}={_trim(text)}")
    return _DetailBlock(tuple(lines), truncated)


def _build_span_tree(events: list[dict[str, Any]]) -> dict[str | None, list[int]]:
    """Index ``sequence`` by ``parent_span_id`` so we can render the tree.

    Roots (``parent_span_id is None``) are returned under the ``None`` key.
    """
    children: dict[str | None, list[int]] = {}
    for i, e in enumerate(events):
        parent = e.get("parent_span_id")
        children.setdefault(parent, []).append(i)
    return children


def _is_root_kind(ep: str) -> bool:
    """Roots get the ``▸`` glyph; everything else ``↳``.

    The transport / lifecycle outer ring is the operator's entry point;
    everything inside is a child step in that ring.
    """
    return ep.startswith("transport.") or ep.startswith("kernel.run.") or ep == "lifecycle.finally"


def _parse_when(event: dict[str, Any]) -> datetime | None:
    raw = event.get("when")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _format_delta_ms(delta_ms: int) -> str:
    sign = "+" if delta_ms >= 0 else "-"
    ms = abs(delta_ms)
    if ms >= 1000:
        return f"Δ{sign}{ms / 1000:.1f}s"
    return f"Δ{sign}{ms}ms"


def _format_abs(when: datetime | None) -> str:
    if when is None:
        return " " * _TIME_CELL_WIDTH
    text = when.strftime("%H:%M:%S")
    if when.microsecond:
        text += f".{when.microsecond // 1000:03d}"
    return text.ljust(_TIME_CELL_WIDTH)


def _render_human(
    events: list[dict[str, Any]],
    *,
    max_detail_per_node: int = 8,
) -> str:
    """Render the spine ``events.jsonl`` as a tree-shaped human timeline.

    Walks ``parent_span_id`` recursively (top-level transport / kernel /
    lifecycle, then per-span children). Per EP, renders a headline via
    ``_event_kind`` and payload text via ``_detail_lines``. Three
    high-volume EPs fold into one line each (token streams, reducer
    streams, transport pairs) but never lose their payload text.
    """
    if not events:
        return "(no events)"

    # Anchor time = the earliest event we have so Δms is meaningful.
    anchored = [e for e in events if _parse_when(e) is not None]
    anchor = min((_parse_when(e) for e in anchored), default=None)
    if anchor is None:
        return "(no timestamps)"

    children = _build_span_tree(events)
    output: list[str] = []

    # Header — first kernel.run.start's payload carries run_id + trace_id.
    run_id = events[0].get("run_id", "?")
    trace_id = next(
        (
            str(e.get("payload", {}).get("trace_id"))
            for e in events
            if isinstance(e.get("payload"), dict) and e["payload"].get("trace_id")
        ),
        "?",
    )
    last_t = max((_parse_when(e) for e in anchored), default=anchor)
    total_ms = int((last_t - anchor).total_seconds() * 1000)
    output.append(f"▶ {run_id}  trace={trace_id}  ·持续 {_format_delta_ms(total_ms).lstrip('Δ+')}")
    output.append("")

    def _walk(parent: str | None, depth: int, marker: str) -> None:
        kids = children.get(parent, [])
        if not kids:
            return
        rendered: set[int] = set()
        i = 0
        while i < len(kids):
            idx = kids[i]
            if idx in rendered:
                i += 1
                continue
            ep_name = events[idx].get("execution_point", "")
            if ep_name == "llm.stream.token":
                j = i
                while (
                    j + 1 < len(kids)
                    and events[kids[j + 1]].get("execution_point") == "llm.stream.token"
                    and events[kids[j + 1]].get("parent_span_id") == parent
                ):
                    j += 1
                block = kids[i : j + 1]
                rendered.update(block)
                output.append(_build_fold_line(events, block, ep_name, depth, anchor))
                i = j + 1
                continue
            if ep_name == "runtime.reducer.apply":
                j = i
                while (
                    j + 1 < len(kids)
                    and events[kids[j + 1]].get("execution_point") == "runtime.reducer.apply"
                    and events[kids[j + 1]].get("parent_span_id") == parent
                ):
                    j += 1
                block = kids[i : j + 1]
                rendered.update(block)
                output.append(_build_fold_line(events, block, ep_name, depth, anchor))
                i = j + 1
                continue
            if ep_name == "transport.route.enter" and i + 1 < len(kids):
                nxt_idx = kids[i + 1]
                if events[nxt_idx].get("execution_point") == "transport.route.exit":
                    rendered.add(idx)
                    rendered.add(nxt_idx)
                    output.append(
                        _render_transport_pair(events, idx, nxt_idx, depth, anchor)
                    )
                    i += 2
                    continue
            rendered.add(idx)
            output.append(
                _render_single(
                    events[idx],
                    marker=marker,
                    depth=depth,
                    anchor=anchor,
                    max_detail_per_node=max_detail_per_node,
                )
            )
            i += 1

    # Walk roots: ``parent_span_id is None``.
    roots = children.get(None, [])
    for idx in roots:
        e = events[idx]
        output.append(
            _render_single(
                e,
                marker="▸",
                depth=0,
                anchor=anchor,
                max_detail_per_node=max_detail_per_node,
            )
        )
        _walk(e.get("span_id"), 1, marker="↳")

    # Footer summary — count EPs that matter to the operator.
    ep_counter: dict[str, int] = {}
    for e in events:
        ep_counter[e.get("execution_point", "?")] = ep_counter.get(e.get("execution_point", "?"), 0) + 1
    exceptions = ep_counter.get("exception.caught", 0)
    tools = ep_counter.get("phase.tool.call.end", 0)
    llms = ep_counter.get("llm.call.start", 0)
    phase_nodes = ep_counter.get("phase_graph.node.start", 0)
    summary = (
        f"▶ run done · {phase_nodes} phase nodes · {llms} llm call"
        f" · {tools} tool call · {exceptions} exception"
        f" · {len(events)} events · {_format_delta_ms(total_ms).lstrip('Δ+')}"
    )
    output.append("")
    output.append(summary)
    return "\n".join(output) + "\n"


def _render_single(
    event: dict[str, Any],
    *,
    marker: str,
    depth: int,
    anchor: datetime,
    max_detail_per_node: int,
) -> str:
    when = _parse_when(event)
    delta_ms = int(((when - anchor).total_seconds() * 1000)) if when else 0
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    ep = event.get("execution_point", "?")
    kind = _event_kind(ep, payload, event.get("outcome"))
    line = (
        f"{_format_abs(when)}"
        f"  {_format_delta_ms(delta_ms):<{_DELTA_WIDTH}}"
        f"  {marker} {kind}"
    )
    block = _detail_lines(ep, payload, max_lines=max_detail_per_node)
    out = [line, *block.lines]
    if block.truncated:
        # ``… (+N more lines)`` so the operator knows detail was elided
        # and where to re-run with ``--max-detail-per-node`` raised.
        out.append(f"  … (+{_estimate_extra(ep, payload)} more lines)")
    return "\n".join(out)


def _estimate_extra(ep: str, payload: dict[str, Any]) -> int:
    """Rough estimate of how many more lines the EP would emit without the cap."""
    if not payload:
        return 0
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return 1
    return max(0, len(text.splitlines()) - 1)


def _build_fold_line(
    events: list[dict[str, Any]],
    indices: list[int],
    ep_name: str,
    depth: int,
    anchor: datetime,
) -> str | None:
    if not indices:
        return None
    head = events[indices[0]]
    tail = events[indices[-1]]
    head_t = _parse_when(head)
    tail_t = _parse_when(tail)
    delta_ms = int(((tail_t - head_t).total_seconds() * 1000)) if head_t and tail_t else 0
    indent = "  " * depth
    if ep_name == "llm.stream.token":
        text = "".join(str(events[idx].get("payload", {}).get("text_delta", "")) for idx in indices)
        chars = sum(len(str(events[idx].get("payload", {}).get("text_delta", ""))) for idx in indices)
        return (
            f"{indent}    llm.stream.token ×{len(indices)}"
            f"  ·{chars} chars"
            f"  \"{text}\""
        )
    if ep_name == "runtime.reducer.apply":
        methods = [
            str(events[idx].get("payload", {}).get("method", "?")) for idx in indices
        ]
        return (
            f"{indent}    runtime.reducer.apply ×{len(indices)}"
            f"  ({', '.join(methods)})  Δ+{delta_ms}ms"
        )
    return None


def _render_transport_pair(
    events: list[dict[str, Any]],
    in_idx: int,
    out_idx: int,
    depth: int,
    anchor: datetime,
) -> str:
    e_in = events[in_idx]
    e_out = events[out_idx]
    t_in = _parse_when(e_in)
    t_out = _parse_when(e_out)
    delta_ms = int(((t_out - t_in).total_seconds() * 1000)) if t_in and t_out else 0
    indent = "  " * depth
    return (
        f"{indent}  {e_in.get('payload', {}).get('method', '?')}"
        f" {e_in.get('payload', {}).get('path', '?')}"
        f" →{e_out.get('payload', {}).get('status', '?')}"
        f"  {_format_delta_ms(delta_ms)}"
    )


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
