"""observability.facade — facade subpackage.

ADR-0169 §D9 删除清单 PR-26 清理:移除 ``step_open / step_close /
step_record_thinking / step_record_tool_call / step_record_tool_result /
step_record_reflect / step_record_span`` 共 7 个 facade 转发方法。
业务路径改走 ``cursor.advance(phase)`` + ``cursor.record_*(...)``;
``StepCoordinator`` 仍保留为 readonly 装配层(供 fixture / 兼容路径)。
"""

from lca.infrastructure.observability.facade.facade import (
    BoundObservability,
    EvidenceBinding,
    OperationRecorder,
    RunContext,
    SpanContextInfo,
    annotate,
    bind,
    bind_backends,
    current_bound,
    current_context,
    detached_span,
    get_span_context,
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
    "RunContext",
    "SpanContextInfo",
    "annotate",
    "bind",
    "bind_backends",
    "current_bound",
    "current_context",
    "detached_span",
    "get_span_context",
    "record",
    "record_operation",
    "record_runtime",
    "set_actor",
    "set_session",
    "span",
]
