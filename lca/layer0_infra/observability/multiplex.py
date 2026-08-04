"""Fan-out Observability: emit each span to multiple backends."""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability


class MultiplexObservability(Observability):
    """Compose multiple Observability backends (e.g. console + collector)."""

    name = "multiplex"

    def __init__(self, backends: Sequence[Observability]) -> None:
        self._backends = list(backends)
        if not self._backends:
            raise ValueError("MultiplexObservability requires at least one backend")

    def emit_span(self, span: TraceSpan) -> None:
        for backend in self._backends:
            backend.emit_span(span)

    @property
    def backends(self) -> list[Observability]:
        return list(self._backends)
