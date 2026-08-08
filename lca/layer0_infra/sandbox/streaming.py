"""Sandbox execution-stream journal emissions (sole record site for SandboxOutputDelta).

Adapters (E2B / local / Mock) call into this module so AST emitter guards stay
package-scoped and all implementations share one seq/stream convention.
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import SandboxOutputDelta
from lca.layer0_infra.observability import record

STREAM_STDOUT = "stdout"
STREAM_STDERR = "stderr"


class SandboxStreamEmitter:
    """Monotonic seq across stdout/stderr for one ``invocation_id``."""

    def __init__(self, invocation_id: str) -> None:
        self._invocation_id = invocation_id or ""
        self._seq = 0

    @property
    def invocation_id(self) -> str:
        return self._invocation_id

    def emit(self, stream: str, text: str) -> None:
        """Record one chunk; no-ops when invocation_id is empty (non-streamed runs)."""
        if not self._invocation_id:
            return
        chunk = text if text is not None else ""
        if chunk == "":
            return
        record(
            SandboxOutputDelta(
                invocation_id=self._invocation_id,
                stream=stream,
                text_delta=chunk,
                seq=self._seq,
            )
        )
        self._seq += 1

    def emit_stdout(self, text: str) -> None:
        self.emit(STREAM_STDOUT, text)

    def emit_stderr(self, text: str) -> None:
        self.emit(STREAM_STDERR, text)
