"""observability.facade — facade subpackage.

ADR-0167 D11 简化: 移除 ``step_close_document`` / ``step_get_lifecycle_store``。
facade 的 step API 只负责转发到 StepCoordinator; document 收口由
``StepTreeAccumulatorDeriver.flush`` 完成(transport 在 terminalize 触发)。
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
    record,
    record_operation,
    record_runtime,
    set_actor,
    set_session,
    span,
    step_close,
    step_open,
    step_record_reflect,
    step_record_span,
    step_record_thinking,
    step_record_tool_call,
    step_record_tool_result,
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
    "record",
    "record_operation",
    "record_runtime",
    "set_actor",
    "set_session",
    "span",
    "step_close",
    "step_open",
    "step_record_reflect",
    "step_record_span",
    "step_record_thinking",
    "step_record_tool_call",
    "step_record_tool_result",
]
