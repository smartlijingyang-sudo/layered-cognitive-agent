# RETAINED(test/CLI/capability; tracking: ADR-0186 PR-3g / I-SESSION-5)
# Production step_tree uses StepTreeFoldDeriver (I-SESSION-5 fold-only builder).
# This package keeps on_event deriver implementations for unit tests,
# CLI replay, and capability provide — not the EventSpine.subscribe
# production builder path.

"""Spine derivers sub-package — see ADR-0165 / ADR-0165.1 / ADR-0167 D9.

Derivers are best-effort consumers that produce secondary artefacts
(step-tree, narrative, live tail, graph, otel_trace, waterfall, ...)
from the event stream. Per FD-2 their exceptions are contained by the
spine. Production step_tree is fold-only (I-SESSION-5).
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
