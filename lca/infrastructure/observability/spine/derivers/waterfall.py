# COMPAT(delete-when: ADR-0186 PR-3g waterfall fold 替代 callback deriver,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# waterfall 是 on_event 累积 → 静态 HTML。收口时改为 SpineReader snapshot
# fold 渲染（events → render），不再需要 callback 订阅。CLI
# ``lca-ops journal trajectory`` 保留，底层数据源迁 snapshot。

"""Waterfall HTML deriver —— DSH Trajectory 风格（ADR-0167 D9 + ADR-0185 PR-3）。

订阅 ``EventSpine``，on flush 渲染一份静态 HTML：
- 每条 spine event 一行（按 sequence 升序）
- 时间轴 / 状态色 / token 切片
- 每个 think 段的 "model saw" 链接由 caller 传入的 ``model_visible_root``
  拼接:PR-3 起默认指向 ``<run_id>.spine.jsonl``(fold SSOT,
  ``foldRequestHeader`` 重建;见 ADR-0185 §3.7);双轨期仍可传
  ``<run_dir>/model_visible/step_N/``(fallback sidecar,PR-4 收口删除)。

不绑 LobeHub / WebServer;CLI 仅 ``lca-ops journal trajectory <run_id>``。
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from lca.infrastructure.observability.spine.event_record import EventRecord

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


class WaterfallDeriver:
    """积累 events，render HTML waterfall。

    HTML 是纯静态：可 host 离线（file://）。不依赖 JS / Tailwind。
    """

    def __init__(self, run_id: str, model_visible_root: Path | None = None) -> None:
        self.run_id = run_id
        self._events: list[EventRecord] = []
        self.model_visible_root = model_visible_root

    def on_event(self, event: EventRecord) -> None:
        if event.run_id == self.run_id:
            self._events.append(event)

    def render(self) -> str:
        if not self._events:
            return self._empty_doc()
        events = sorted(self._events, key=lambda e: e.sequence)
        rows: list[str] = []
        for e in events:
            rows.append(self._row(e))
        body = "\n".join(rows)
        return self._doc(body)

    def write(self, path: Path) -> Path:
        text = self.render()
        path.write_text(text, encoding="utf-8")
        return path

    def _row(self, e: EventRecord) -> str:
        glyph = _EP_GLYPH.get(e.execution_point, "·")
        outcome_cls = ""
        if e.outcome == "failure":
            outcome_cls = ' class="fail"'
        elif e.outcome == "success":
            outcome_cls = ' class="ok"'
        ts = e.when.isoformat() if e.when else ""
        payload = self._payload_preview(e)
        # 链接目标 = model_visible_root + step 子路径;root 语义由 caller 定:
        # PR-3 起默认 <run_id>.spine.jsonl(fold SSOT),双轨期可 fallback
        # <run_dir>/model_visible/(PR-4 收口删除)。
        step_link = ""
        if (
            self.model_visible_root is not None
            and e.step_id
            and e.execution_point in {"llm.call.start", "writable.segment.start"}
        ):
            step_link = (
                f'<a href="file://{self.model_visible_root}/step_{e.step_id}/system-prompt.md">'
                "model saw</a>"
            )
        return (
            f"<tr{outcome_cls}>"
            f'<td class="seq">{e.sequence}</td>'
            f'<td class="ts">{escape(ts)}</td>'
            f'<td class="ep"><span class="glyph">{glyph}</span> '
            f"{escape(e.execution_point)}</td>"
            f'<td class="step">{escape(str(e.step_id or ""))}</td>'
            f'<td class="payload">{escape(payload)}</td>'
            f'<td class="link">{step_link}</td>'
            "</tr>"
        )

    @staticmethod
    def _payload_preview(e: EventRecord) -> str:
        keys = ("model", "tool_name", "summary", "outcome", "kind")
        bits = [f"{k}={escape(str(e.payload.get(k, '')))[:60]}" for k in keys if k in e.payload]
        return "; ".join(bits)

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


__all__ = ["WaterfallDeriver"]
