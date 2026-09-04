# COMPAT(delete-when: ADR-0186 PR-3g 残留 on_event callback deriver 清零,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# 本包保留旧 EventSpine on_event deriver 实现。生产 step_tree 已走
# StepTreeFoldDeriver；capability / CLI / 测试仍引用时保留本包。

"""Spine derivers sub-package — see ADR-0165 / ADR-0165.1 / ADR-0167 D9.

Derivers are best-effort subscribers that produce secondary artefacts
(step-tree, narrative, live tail, graph, otel_trace, waterfall, ...)
from the canonical event stream. Per FD-2 their exceptions are contained
by the spine.
"""

from __future__ import annotations

from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.derivers.graph import GraphDeriver
from lca.infrastructure.observability.spine.derivers.otel_trace import (
    OtelSpan,
    OtelTraceDeriver,
)
from lca.infrastructure.observability.spine.derivers.waterfall import (
    WaterfallDeriver,
)

__all__ = [
    "Deriver",
    "GraphDeriver",
    "OtelSpan",
    "OtelTraceDeriver",
    "WaterfallDeriver",
]
