"""Runtime-layer session surface (PR2, ADR-0226 §1).

Owns the run-scoped writer that becomes the single surface-write seam in
PR2 (replaces the dual ContextVar-bound mechanism deleted in Task 3).
"""

from lca.runtime.session.run_session_writer import (
    RunSessionWriter,
    SessionWriterUnboundError,
)

__all__ = ["RunSessionWriter", "SessionWriterUnboundError"]
