"""JSONL record decoding and I17 column extraction for ``journal trace``.

``_iter_events`` decodes one spine ledger line per yielded event;
``_extract_source_location`` / ``_extract_next_frame`` / ``_render_locals``
project the I17 source columns (``source_location`` / ``call_frames`` /
``locals_snapshot``) into the :class:`TraceRow` DTO that the table
renderer consumes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.infrastructure.cli.commands.journal import spine_event_when

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
    """Yield one decoded record per line of spine ledger.

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
        when=spine_event_when(event),
        source_file=file_value,
        source_line=line_value,
        source_function=function_value,
        next_frame=next_frame,
        locals_render=locals_render,
    )
