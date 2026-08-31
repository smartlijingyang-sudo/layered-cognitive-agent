"""observability.facade — facade subpackage."""

from lca.infrastructure.observability.facade.facade import (
    BoundObservability,
    EvidenceBinding,
    OperationRecorder,
    SpanContextInfo,
    annotate,
    bind,
    bind_backends,
    current_bound,
    current_context,
    record,
    record_operation,
    record_runtime,
    set_actor,
    set_session,
    span,
)

__all__ = [
    "BoundObservability",
    "EvidenceBinding",
    "OperationRecorder",
    "SpanContextInfo",
    "annotate",
    "bind",
    "bind_backends",
    "current_bound",
    "current_context",
    "record",
    "record_operation",
    "record_runtime",
    "set_actor",
    "set_session",
    "span",
]
