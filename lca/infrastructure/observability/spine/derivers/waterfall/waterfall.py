# RETAINED(test/CLI/capability; tracking: ADR-0186 PR-3g / I-SESSION-5)
# Production step_tree uses StepTreeFoldDeriver (I-SESSION-5 fold-only builder).
# Waterfall accumulates on_event → static HTML for CLI
# ``lca-ops journal trajectory``. Not on the EventSpine.subscribe
# production builder path; kept for unit tests, CLI replay, and
# capability provide.

"""Waterfall HTML deriver (DSH Trajectory style; ADR-0167 D9 + ADR-0185 PR-3).

Consumes spine events; on flush renders static HTML:
- one row per spine event (sorted by ts)
- time axis, outcome-coloured row, glyph per EP family
- per-think-step "model saw" link built from caller-supplied
  ``model_visible_root`` (default points at the spine fold SSOT)

Accepts either ``EventRecord`` (strict typed) or a raw dict
(``SpineRow``) carrying the same fields. Real spine rows no longer
satisfy the strict ``EventRecord`` schema (sequence / span_id /
when / epoch / causality_id are absent; category / event_hash /
trace_id are present), so the CLI layer feeds dicts through
``on_event``. The deriver normalizes both shapes into a single
internal row view, keeping the public surface tolerant.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, TypedDict

from lca.infrastructure.observability.spine.event.record import EventRecord

_EP_GLYPH: dict[str, str] = {
    "writable.step.start": "▶",
    "writable.step.end": "■",
    "writable.segment.start": "·",
    "writable.segment.end": "·",
    "llm.call.start": "🧠",
    "llm.call.end": "🧠",
    "llm.stream.token": "·",
    "body.tool.execute.start": "🔧",
    "body.tool.execute.end": "🔧",
    "phase.tool.call.start": "🔧",
    "phase.tool.call.end": "🔧",
    "phase.tool.denied": "🚫",
    "phase.act.fold.start": "⚙",
    "phase.act.fold.end": "⚙",
    "phase.perceive.fold": "👁",
    "phase.think.fold": "🧠",
    "phase.remember.fold": "💭",
    "phase.reflect.fold": "🪞",
    "phase.stop.fold": "🛑",
    "kernel.run.start": "▶",
    "kernel.run.stop": "■",
}


class _Row(TypedDict, total=False):
    execution_point: str
    ts: str
    outcome: str
    step_id: str
    payload: dict[str, Any]
    seq: int


def _coerce(event: EventRecord | dict[str, Any]) -> _Row | None:
    """Normalize EventRecord or dict to the deriver's internal row view.

    Returns None only when the input is missing the `execution_point`
    field — that is the one field every waterfall row needs.
    """
    if isinstance(event, dict):
        ep = str(event.get("execution_point") or "")
        if not ep:
            return None
        payload = event.get("payload") or {}
        payload = payload if isinstance(payload, dict) else {}
        return {
            "execution_point": ep,
            "ts": str(event.get("ts") or event.get("when") or ""),
            "outcome": str(event.get("outcome") or payload.get("outcome") or ""),
            "step_id": str(event.get("step_id") or payload.get("step_id") or ""),
            "payload": payload,
            "seq": int(event.get("sequence") or event.get("event_seq") or 0),
        }

    ep = str(getattr(event, "execution_point", "") or "")
    if not ep:
        return None
    payload = getattr(event, "payload", {}) or {}
    when = getattr(event, "when", None)
    ts = when.isoformat() if when else ""
    return {
        "execution_point": ep,
        "ts": ts,
        "outcome": str(getattr(event, "outcome", "") or ""),
        "step_id": str(getattr(event, "step_id", "") or ""),
        "payload": payload,
        "seq": int(getattr(event, "sequence", 0) or 0),
    }


class WaterfallDeriver:
    """Accumulate events, render HTML waterfall.

    HTML is static, self-contained (no JS / no CDN). Can be served from
    ``file://``. Not bound to LobeHub / WebServer; CLI only:
    ``lca-ops journal trajectory <run_id>``.
    """

    def __init__(self, run_id: str, model_visible_root: Path | None = None) -> None:
        self.run_id = run_id
        self._events: list[_Row] = []
        self.model_visible_root = model_visible_root

    def on_event(self, event: EventRecord | dict[str, Any]) -> None:
        row = _coerce(event)
        if row is None:
            return
        self._events.append(row)

    def render(self) -> str:
        if not self._events:
            return self._empty_doc()
        events = sorted(self._events, key=_sort_key)
        rows: list[str] = [self._row(e) for e in events]
        body = "\n".join(rows)
        return self._doc(body)

    def write(self, path: Path) -> Path:
        text = self.render()
        path.write_text(text, encoding="utf-8")
        return path

    def _row(self, e: _Row) -> str:
        glyph = _EP_GLYPH.get(e["execution_point"], "·")
        outcome_cls = ""
        if e["outcome"].lower() == "failure":
            outcome_cls = ' class="fail"'
        elif e["outcome"].lower() == "success":
            outcome_cls = ' class="ok"'
        payload = _payload_preview(e["payload"])
        step_link = ""
        if (
            self.model_visible_root is not None
            and e["step_id"]
            and e["execution_point"] in {"llm.call.start", "writable.segment.start"}
        ):
            step_link = (
                f'<a href="file://{self.model_visible_root}/step_{e["step_id"]}/'
                "system-prompt.md\">model saw</a>"
            )
        return (
            f"<tr{outcome_cls}>"
            f'<td class="seq">{e["seq"]}</td>'
            f'<td class="ts">{escape(e["ts"])}</td>'
            f'<td class="ep"><span class="glyph">{glyph}</span> '
            f"{escape(e['execution_point'])}</td>"
            f'<td class="step">{escape(e["step_id"])}</td>'
            f'<td class="payload">{escape(payload)}</td>'
            f'<td class="link">{step_link}</td>'
            "</tr>"
        )

    def _empty_doc(self) -> str:
        return self._doc('<tr><td colspan="6">(no events)</td></tr>')

    def _doc(self, body: str) -> str:
        return (
            "<!doctype html>\n"
            '<meta charset="utf-8">\n'
            "<title>Trajectory — " + escape(self.run_id) + "</title>\n"
            "<style>\n"
            "body{font-family:ui-monospace,monospace;margin:16px}\n"
            "table{border-collapse:collapse;width:100%}\n"
            "th,td{border-bottom:1px solid #eee;padding:4px 8px;text-align:left;vertical-align:top}\n"
            "tr.ok{background:#f7fff7}\n"
            "tr.fail{background:#fff0f0}\n"
            ".seq{color:#888;width:48px}\n"
            ".ts{color:#888;width:200px}\n"
            ".ep{width:240px;font-weight:600}\n"
            ".step{color:#666;width:120px}\n"
            ".payload{font-size:12px;color:#333}\n"
            ".glyph{width:18px;display:inline-block}\n"
            "</style>\n"
            "<h1>Trajectory — " + escape(self.run_id) + "</h1>\n"
            "<table><thead><tr>"
            "<th>#</th><th>ts</th><th>execution_point</th>"
            "<th>step</th><th>payload</th><th>model saw</th>"
            "</tr></thead>\n<tbody>\n" + body + "\n</tbody></table>\n"
        )


def _sort_key(e: _Row) -> tuple[int, str]:
    return (e.get("seq") or 0, e.get("ts") or "")


def _payload_preview(payload: dict[str, Any]) -> str:
    keys = ("model", "tool_name", "summary", "outcome", "kind", "node_id")
    bits: list[str] = []
    for k in keys:
        if k in payload:
            v = str(payload[k])[:60]
            bits.append(f"{k}={escape(v)}")
    return "; ".join(bits)


__all__ = ["WaterfallDeriver"]
