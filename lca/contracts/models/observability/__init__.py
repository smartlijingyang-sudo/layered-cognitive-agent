"""models/observability — contracts 内部子包（依赖方向由 import-linter 契约强制）。"""

from lca.contracts.models.observability.journal_doc import (
    JournalDocument,
    JournalMetadata,
    append_step,
    close_document,
    empty_document,
)
from lca.contracts.models.observability.journal_step import (
    AttachmentRef,
    JournalStep,
    ReflectTrace,
    SpanRecord,
    StepContext,
    StepOutcome,
    StepPhase,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    compute_duration_ms,
    make_step_id,
    summarize_step,
)
from lca.contracts.models.observability.plan_ref import (
    get_current_plan_ref,
    plan_ref_scope,
    reset_current_plan_ref,
    set_current_plan_ref,
    stamped_event_has_plan_ref,
)

__all__ = [
    # step-tree (ADR-0164 草案)
    "AttachmentRef",
    "JournalDocument",
    "JournalMetadata",
    "JournalStep",
    "ReflectTrace",
    "SpanRecord",
    "StepContext",
    "StepOutcome",
    "StepPhase",
    "ThinkingTrace",
    "ToolCallRecord",
    "ToolResult",
    "append_step",
    "close_document",
    "compute_duration_ms",
    "empty_document",
    # plan_ref (legacy export)
    "get_current_plan_ref",
    "make_step_id",
    "plan_ref_scope",
    "reset_current_plan_ref",
    "set_current_plan_ref",
    "stamped_event_has_plan_ref",
    "summarize_step",
]
