"""Console 叙述导出器 —— 框架默认人类视图。

层次：
  1) run.plan 场景卡（strategy / members / plan / task）
  2) 按角色分节（── Lead · step 0 ──）
  3) 节内全量 span 一行一条（对齐、缩进）
  4) 根 span 结束时输出运行 digest（5 秒定位异常 run）
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any, TextIO

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from lca.contracts.telemetry import ATTR_STATUS, SpanName
from lca.layer0_infra.observability.narrative import (
    format_run_plan_card,
    format_section_header,
    format_span_line,
    logical_depth,
    section_key_for_span,
)
from lca.layer0_infra.observability.view import SpanView, view_of

_TOP_SLOWEST = 3
"""digest 中展示的最慢 span 数。"""
_MAX_BUFFERED_TRACES = 64
"""并发 trace 缓冲上限（超出丢弃最旧，防内存膨胀）。"""


class _RunDigest:
    """单个 trace 的运行期统计（根 span 结束时渲染）。"""

    def __init__(self) -> None:
        self.span_count = 0
        self.error_count = 0
        self.slowest: list[tuple[int, str]] = []
        self.status = ""
        self.duration_ms = 0

    def observe(self, view: SpanView) -> None:
        self.span_count += 1
        if view.status != "ok":
            self.error_count += 1
        self.slowest.append((view.duration_ms, view.name))
        self.slowest.sort(key=lambda item: item[0], reverse=True)
        self.slowest = self.slowest[:_TOP_SLOWEST]
        status = view.attributes.get(ATTR_STATUS)
        if status:
            self.status = str(status)

    def render(self) -> str:
        slow = ", ".join(f"{name} {dur}ms" for dur, name in self.slowest)
        head = (
            f"\n── digest ── spans={self.span_count} errors={self.error_count} "
            f"duration={self.duration_ms}ms"
        )
        if self.status:
            head += f" status={self.status}"
        return f"{head}\n   slowest: {slow}" if slow else head


class ConsoleNarratorExporter(SpanExporter):
    """Stdout human progress — full spans, one style, clear hierarchy."""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._section: str | None = None
        self._digests: dict[str, _RunDigest] = {}

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        for readable in spans:
            self.emit_view(view_of(readable))
        return SpanExportResult.SUCCESS

    def emit_view(self, view: SpanView) -> None:
        """渲染一个 SpanView（测试可直接投喂，无需 OTel 包装）。"""
        out = self._stream
        digest = self._digests.setdefault(view.trace_id, _RunDigest())
        if len(self._digests) > _MAX_BUFFERED_TRACES:
            self._digests.pop(next(iter(self._digests)))
        digest.observe(view)

        if view.name == SpanName.RUN_PLAN.value:
            print(format_run_plan_card(view), file=out, flush=True)
            self._section = None
        else:
            self._emit_section_line(view)
            self._emit_events(view)

        if view.parent_span_id is None:  # 根 span 结束 → digest 收尾
            digest.duration_ms = view.duration_ms
            print(digest.render(), file=out, flush=True)
            self._digests.pop(view.trace_id, None)

    def _emit_section_line(self, view: SpanView) -> None:
        out = self._stream
        key = section_key_for_span(view)
        if self._section is not None:
            # Same actor: don't bounce "Alice · step 0" ↔ "Alice" for run.agent/hooks
            prev_actor = self._section.split(" · ", 1)[0]
            next_actor = key.split(" · ", 1)[0]
            if prev_actor == next_actor and " · " not in key and " · " in self._section:
                key = self._section
        if key != self._section:
            print(format_section_header(key), file=out, flush=True)
            self._section = key
        print(format_span_line(view, depth=logical_depth(view)), file=out, flush=True)

    def _emit_events(self, view: SpanView) -> None:
        for name, attrs in view.events:
            bits = " ".join(f"{k}={v}" for k, v in attrs.items())
            suffix = f"  {bits}" if bits else ""
            print(f"    ◇ {name}{suffix}", file=self._stream, flush=True)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True
