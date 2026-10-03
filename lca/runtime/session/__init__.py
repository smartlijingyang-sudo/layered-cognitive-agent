"""Runtime-layer session surface (PR2, ADR-0226 §1).

Owns the run-scoped writer that becomes the single surface-write seam in
PR2 (replaces the dual ContextVar-bound mechanism deleted in Task 3).
"""

from lca.runtime.session.run_session_writer import (
    RunSessionWriter,
    SessionWriterUnboundError,
    ensure_intent_widget_in_assistant_message,
    extract_pending_intents_from_events,
)

__all__ = [
    "RunSessionWriter",
    "SessionWriterUnboundError",
    "ensure_intent_widget_in_assistant_message",
    "extract_pending_intents_from_events",
]
