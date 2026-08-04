"""No-op Observability for tests that do not care about spans."""

from __future__ import annotations

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability


class NullObservability(Observability):
    name = "null"

    def emit_span(self, span: TraceSpan) -> None:
        return None
