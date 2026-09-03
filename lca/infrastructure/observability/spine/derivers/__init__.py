# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine deriver；PR-8 shim 走 events/subscribers/spine_* 包装；
# 本模块保留至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.derivers" lca/ = 0 触发）。

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
