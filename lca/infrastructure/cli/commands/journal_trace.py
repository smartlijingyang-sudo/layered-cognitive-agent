"""Journal trace — print one event per line, optionally with I17 source columns.

Task 9.3: ``./scripts/lca-ops journal trace [run_id] [--locals] [--source]``
reads the append-only spine ledger written by the spine ``FileSink``
and prints a human-readable table. ``run_id`` is optional: when omitted
the command picks the latest run via ``traces/latest.json`` (pointer
preferred, mtime-sorted fallback). The default view shows ``seq /
execution point / channel / outcome / when``. With ``--source`` two extra
columns appear (``source_location`` file:line and the function name).
With ``--locals`` (which implies ``--source``) two more columns are
added: the first ``call_frames`` entry beyond ``source_location`` and a
compact ``locals_snapshot.pre_call`` rendering.

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
  hide I17 violations. If the spine ledger is missing the CLI emits a
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
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.commands._shared import find_latest_run_id
from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI default traces root
_DEFAULT_MAX_DETAIL_PER_NODE = 8

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
    """Yield one decoded record per line of the spine ledger.

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
    """Project one spine ledger line into a :class:`TraceRow`."""
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
# The view layer below translates the spine ledger SSOT into a
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
        return f"body.sandbox.enter  invocation={payload.get('invocation_id', '?')[:16]}"
    if ep == "body.sandbox.exit":
        return f"body.sandbox.exit  invocation={payload.get('invocation_id', '?')[:16]}"
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
        return f"prompt_assembler.assemble.start  template={payload.get('template_id', '?')}"
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
        return f"runtime.event_publisher.publish  event_type={payload.get('event_type', '?')}"
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
        if payload.get("error_type") or payload.get("exception_message"):
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
    skip = _KIND_KEYS.get(ep, frozenset())
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        if key in skip:
            continue  # already surfaced in the headline
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(value)
        _add(f"  {key}={_trim(text)}")
    return _DetailBlock(tuple(lines), truncated)


# Keys already surfaced in the ``_event_kind`` headline for each EP.
# The fallback ``key=value`` dump must skip these so the headline is
# not duplicated line-for-line in the detail block.
_KIND_KEYS: dict[str, frozenset[str]] = {
    "kernel.run.start": frozenset({"run_id", "trace_id"}),
    "kernel.run.stop": frozenset(),
    "agent_loop.iteration.start": frozenset({"trace_id", "role", "iteration_kind"}),
    "agent_loop.iteration.end": frozenset({"trace_id", "role", "iteration_kind"}),
    "phase_graph.node.start": frozenset({"span_id", "parent_span_id", "signature_fingerprint"}),
    "phase_graph.node.end": frozenset(
        {"span_id", "parent_span_id", "error_type", "exception_message", "traceback_snippet"}
    ),
    "transport.route.enter": frozenset({"path", "method", "run_id"}),
    "transport.route.exit": frozenset({"path", "method", "run_id", "status"}),
    "transport.sse.publish": frozenset(),
    "llm.call.start": frozenset({"model", "stream"}),
    "llm.call.end": frozenset(
        {"model", "stream", "latency_ms", "prompt_tokens", "completion_tokens"}
    ),
    "body.tool.execute.start": frozenset({"tool_name", "attempt", "wrapper", "invocation_id"}),
    "body.tool.execute.end": frozenset({"tool_name", "latency_ms", "invocation_id", "outcome"}),
    "body.sandbox.enter": frozenset({"invocation_id", "tool_name"}),
    "body.sandbox.exit": frozenset({"invocation_id", "tool_name"}),
    "phase.tool.call.start": frozenset({"tool_name", "arguments_summary"}),
    "phase.tool.call.end": frozenset({"tool_name", "ok", "latency_ms", "invocation_id"}),
    "phase.tool.denied": frozenset({"reason"}),
    "phase.perceive.fold": frozenset({"phase", "objective"}),
    "phase.think.fold": frozenset({"phase"}),
    "phase.act.fold.start": frozenset({"tool_name", "objective"}),
    "phase.act.fold.end": frozenset({"outcome", "error"}),
    "brain.think.start": frozenset({"state_id"}),
    "brain.think.end": frozenset({"state_id"}),
    "reasoner.reason.start": frozenset({"state_id"}),
    "reasoner.reason.end": frozenset({"state_id"}),
    "critic.eval.start": frozenset({"state_id"}),
    "critic.eval.end": frozenset({"state_id"}),
    "synthesizer.merge": frozenset({"state_id", "candidate_count"}),
    "skill_router.route": frozenset(),
    "prompt_assembler.assemble.start": frozenset({"state_id", "template_id"}),
    "prompt_assembler.assemble.end": frozenset({"state_id", "template_id", "section_count"}),
    "memory.read": frozenset({"state_id"}),
    "memory.write": frozenset({"state_id", "layer", "record_id"}),
    "runtime.checkpoint.create": frozenset(),
    "runtime.resume.start": frozenset(),
    "runtime.resume.end": frozenset(),
    "runtime.reducer.apply": frozenset({"method", "phase", "run_id"}),
    "runtime.event_publisher.publish": frozenset({"event_type", "trace_id"}),
    "lifecycle.finally": frozenset({"boundary", "trace_id"}),
    "exception.caught": frozenset({"exc_type", "boundary"}),
    "exception.finally": frozenset({"boundary"}),
    "writable.step.start": frozenset(),
    "writable.step.end": frozenset(),
    "writable.segment.start": frozenset(),
    "writable.segment.end": frozenset(),
}


def _build_span_tree(events: list[dict[str, Any]]) -> dict[str | None, list[int]]:
    """Index event positions by ``parent_span_id`` so we can render the tree.

    Two relations live in this map:
    * ``parent is None`` → root ring (transport, kernel.run.*, lifecycle)
    * ``parent = some span id`` → children of that span
    """
    children: dict[str | None, list[int]] = {}
    for i, e in enumerate(events):
        parent = e.get("parent_span_id")
        children.setdefault(parent, []).append(i)
    return children


def _parent_is_lca_span(parent: str | None) -> bool:
    """Real LCA span ids (lca-span-*) carry sub-events; sequence ids do not.

    The spine uses ``lca-span-*`` for phase_graph / agent_loop / real
    component spans and ``lca-seq-*`` as a global sequence counter that
    shows up in many ``parent_span_id`` slots but is NOT a real parent
    for any span. We only descend into a span when its name belongs to
    the ``lca-span-`` namespace.
    """
    return bool(parent) and parent.startswith("lca-span-")


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
    """Render the spine ledger as a tree-shaped human timeline.

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

    def _walk(
        parent: str | None,
        *,
        depth: int,
        marker: str,
    ) -> set[int]:
        """Render children of ``parent``, applying folding rules.

        After rendering each event, recurses into its children when its
        ``span_id`` is a real ``lca-span-*``. Sequence ids are bookkeeping,
        not a parent reference — events hanging off a sequence id are
        still rendered, just at the same depth.
        """
        kids = children.get(parent, [])
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
            if (
                ep_name == "transport.route.enter"
                and i + 1 < len(kids)
                and events[kids[i + 1]].get("execution_point") == "transport.route.exit"
            ):
                nxt_idx = kids[i + 1]
                rendered.add(idx)
                rendered.add(nxt_idx)
                output.append(_render_transport_pair(events, idx, nxt_idx, depth, anchor))
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
            child_span = events[idx].get("span_id")
            if _parent_is_lca_span(child_span):
                rendered |= _walk(child_span, depth=depth + 1, marker="↳")
            i += 1
        return rendered

    # Emit every event in the original ``sequence`` order. Each event's
    # depth comes from how many ``lca-span-*`` ancestors it has — that
    # is the simplest tree that survives both real lca-spans and
    # sequence-id bookkeeping.
    depth_of: dict[int, int] = {}
    span_owner: dict[str, int] = {}
    for idx, e in enumerate(events):
        parent = e.get("parent_span_id")
        depth_of[idx] = depth_of.get(span_owner.get(parent, -1), 0) + (
            1 if _parent_is_lca_span(parent) and parent in span_owner else 0
        )
        if _parent_is_lca_span(e.get("span_id")):
            span_owner[e["span_id"]] = idx

    rendered: set[int] = set()
    i = 0
    while i < len(events):
        idx = i
        if idx in rendered:
            i += 1
            continue
        ep_name = events[idx].get("execution_point", "")
        if ep_name == "llm.stream.token":
            j = i
            while (
                j + 1 < len(events) and events[j + 1].get("execution_point") == "llm.stream.token"
            ):
                j += 1
            block = list(range(i, j + 1))
            rendered.update(block)
            output.append(_build_fold_line(events, block, ep_name, depth_of[idx], anchor))
            i = j + 1
            continue
        if ep_name == "runtime.reducer.apply":
            j = i
            while (
                j + 1 < len(events)
                and events[j + 1].get("execution_point") == "runtime.reducer.apply"
            ):
                j += 1
            block = list(range(i, j + 1))
            rendered.update(block)
            output.append(_build_fold_line(events, block, ep_name, depth_of[idx], anchor))
            i = j + 1
            continue
        if (
            ep_name == "transport.route.enter"
            and i + 1 < len(events)
            and events[i + 1].get("execution_point") == "transport.route.exit"
        ):
            rendered.add(i)
            rendered.add(i + 1)
            output.append(_render_transport_pair(events, i, i + 1, depth_of[idx], anchor))
            i += 2
            continue
        rendered.add(idx)
        depth = depth_of[idx]
        marker = "▸" if depth == 0 else "↳"
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

    # Orphans: events whose ``parent_span_id`` references a span we never
    # saw (parent process died before its child did). Surface them in their
    # own ring so no event is silently dropped. We synthesise a fake parent
    # id so ``_walk`` treats them as siblings at depth 0.
    seen: set[int] = set()
    for kids in children.values():
        seen.update(kids)
    orphans = [i for i in range(len(events)) if i not in seen]
    if orphans:
        output.append("")
        output.append("── orphan events (parent span missing) ──")
        synthetic_key = f"__orphans_{id(orphans)}__"
        children[synthetic_key] = orphans
        _walk(synthetic_key, depth=0, marker="?")

    # Footer summary — count EPs that matter to the operator.
    ep_counter: dict[str, int] = {}
    for e in events:
        ep_counter[e.get("execution_point", "?")] = (
            ep_counter.get(e.get("execution_point", "?"), 0) + 1
        )
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
    delta_ms = int((when - anchor).total_seconds() * 1000) if when else 0
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    ep = event.get("execution_point", "?")
    kind = _event_kind(ep, payload, event.get("outcome"))
    line = f"{_format_abs(when)}  {_format_delta_ms(delta_ms):<{_DELTA_WIDTH}}  {marker} {kind}"
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
    delta_ms = int((tail_t - head_t).total_seconds() * 1000) if head_t and tail_t else 0
    indent = "  " * depth
    if ep_name == "llm.stream.token":
        text = "".join(str(events[idx].get("payload", {}).get("text_delta", "")) for idx in indices)
        chars = sum(
            len(str(events[idx].get("payload", {}).get("text_delta", ""))) for idx in indices
        )
        return f'{indent}    llm.stream.token ×{len(indices)}  ·{chars} chars  "{text}"'
    if ep_name == "runtime.reducer.apply":
        methods = [str(events[idx].get("payload", {}).get("method", "?")) for idx in indices]
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
    delta_ms = int((t_out - t_in).total_seconds() * 1000) if t_in and t_out else 0
    indent = "  " * depth
    return (
        f"{indent}  {e_in.get('payload', {}).get('method', '?')}"
        f" {e_in.get('payload', {}).get('path', '?')}"
        f" →{e_out.get('payload', {}).get('status', '?')}"
        f"  {_format_delta_ms(delta_ms)}"
    )


def _resolve_events_path(traces_root: Path, run_id: str) -> Path:
    """Resolve spine events file under ``<run_dir>`` or surface a friendly error(PR-27)。

    ADR-0169 PR-27 L10:默认 ``<run_id>.spine.jsonl``;若不存在回退到
    :data:`LEGACY_FILE_NAME`(向后兼容)。两者都不存在时给出友好错误。
    """
    locator = FilesystemRunLocator(traces_root)
    run_dir = locator.run_dir(run_id)
    if not run_dir.exists():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        print("  hint: 检查 --traces-root 是否正确,run_id 是否存在", file=sys.stderr)
        raise SystemExit(1)
    spine_path = locator.events_path(run_id)
    if spine_path.exists():
        return spine_path
    # locator.events_path 已包含 legacy 兜底,若仍不存在则提示
    print(
        f"spine events file not found: {spine_path}\n"
        f"  hint: spine FileSink 尚未写入 events,或 run {run_id} 不在 PR-9 之后",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _latest_run_id(traces_root: Path) -> str | None:
    """Resolve the latest ``run_id`` under ``traces_root`` for argument-less trace.

    Delegates to :func:`lca.infrastructure.cli.commands._shared.find_latest_run_id`
    so the resolution rules (``traces/latest.json`` pointer first, then
    mtime-sorted fallback) stay consistent across CLI commands.
    """
    return find_latest_run_id(traces_root)


def register(app: typer.Typer) -> None:
    """Register the ``trace`` command under the ``journal`` group."""

    @app.command(name="trace")
    def trace_cmd(
        run_id: str = typer.Argument(
            "",
            help="run_id (e.g. run_c38532761cfb);空 = 最新一个 run(traces/latest.json 优先)",
        ),
        human: bool = typer.Option(
            True,
            "--human/--no-human",
            help="人读视图(默认开):tree 缩进 + payload 原文 + Δms",
        ),
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
        max_detail_per_node: int = typer.Option(
            _DEFAULT_MAX_DETAIL_PER_NODE,
            "--max-detail-per-node",
            help="人读视图下每个节点最多展开的 payload 行数(超出显示 +N more)",
        ),
    ) -> None:
        """检查一个 run 的 spine ledger(只读,PR-9 I17 起生效)。

        不带参数时自动选最新一个 run(``traces/latest.json`` 原子指针优先,
        否则 mtime 最新)。其余语义同显式传参:

        默认开 ``--human``:tree 缩进 + payload 原文 + Δms 时间戳 +
        自动折叠 ``llm.stream.token`` / ``runtime.reducer.apply`` /
        配对的 ``transport.route.{enter,exit}``,但**不截断 payload 文本**。

        加 ``--no-human`` 回到原表格:``seq / execution_point /
        channel / outcome / when / source``(对 CI / agent 友好)。
        """
        # ``--locals`` implies ``--source`` so the table is consistent:
        # locals without source_location is ambiguous. Only meaningful in
        # the ``--no-human`` path; ignored in ``--human``.
        if with_locals:
            with_source = True

        resolved_run_id = run_id or _latest_run_id(traces_root)
        if not resolved_run_id:
            print(
                "no run_id provided and no runs found under "
                f"{traces_root / 'runs'}; pass a run_id explicitly",
                file=sys.stderr,
            )
            raise SystemExit(1)
        events_path = _resolve_events_path(traces_root, resolved_run_id)
        all_events: list[dict[str, Any]] = []
        for event in _iter_events(events_path):
            if event.get("__decode_error__"):
                continue
            all_events.append(event)

        if limit > 0:
            all_events = all_events[:limit]

        if human and not json_output:
            sys.stdout.write(
                _render_human(
                    all_events,
                    max_detail_per_node=max_detail_per_node,
                )
            )
            return

        rows: list[TraceRow] = []
        skipped = 0
        total = 0
        for event in all_events:
            total += 1
            payload = event.get("payload")
            if not isinstance(payload, dict):
                skipped += 1
                continue
            seq = int(event.get("sequence", 0) or 0)
            rows.append(_event_to_row(seq, event))

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
                "run_id": resolved_run_id,
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
            f"{skipped} skipped (spine={events_path}) ──\n"
        )


__all__ = ["register"]
