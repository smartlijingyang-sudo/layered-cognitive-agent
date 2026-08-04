"""控制台可观测性 —— 框架默认唯一视图：场景卡 + 分节全量 span。

层次：
  1) run.plan 场景卡（strategy / members / plan / task）
  2) 按角色分节（── Lead · step 0 ──）
  3) 节内全量 span 一行一条（对齐、缩进），无 banner 双写
"""

from __future__ import annotations

import sys
from typing import TextIO

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability
from lca.contracts.telemetry import SpanName
from lca.layer0_infra.observability.plan_narrative import format_run_plan_card
from lca.layer0_infra.observability.run_narrative import (
    format_section_header,
    format_span_line,
    logical_depth,
    section_key_for_span,
)


class ConsoleObservability(Observability):
    """Stdout human progress — full spans, one style, clear hierarchy."""

    name = "console"

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._section: str | None = None

    def emit_span(self, span: TraceSpan) -> None:
        out = self._stream
        if span.name == SpanName.RUN_PLAN.value:
            print(format_run_plan_card(span), file=out, flush=True)
            self._section = None
            return

        key = section_key_for_span(span)
        if self._section is not None:
            # Same actor: don't bounce "Alice · step 0" ↔ "Alice" for run.agent/hooks
            prev_actor = self._section.split(" · ", 1)[0]
            next_actor = key.split(" · ", 1)[0]
            if prev_actor == next_actor and " · " not in key and " · " in self._section:
                key = self._section
        if key != self._section:
            print(format_section_header(key), file=out, flush=True)
            self._section = key

        print(format_span_line(span, depth=logical_depth(span)), file=out, flush=True)
