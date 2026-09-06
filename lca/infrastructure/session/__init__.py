"""Session runtime seams consumed by cognition (model context + checkpoint)."""

from lca.infrastructure.session.bindings import (
    assemble_model_history,
    await_model_request_checkpoint,
    await_step_boundary_checkpoint,
    await_tool_side_effect_checkpoint,
    current_model_context_assembler,
    resolve_flushable_session,
    resolve_session_reader,
    set_checkpoint_policy,
    set_model_context_assembler,
)
from lca.infrastructure.session.model_context_assembler import (
    DefaultModelContextAssembler,
)

__all__ = [
    "DefaultModelContextAssembler",
    "assemble_model_history",
    "await_model_request_checkpoint",
    "await_tool_side_effect_checkpoint",
    "current_model_context_assembler",
    "resolve_flushable_session",
    "resolve_session_reader",
    "set_checkpoint_policy",
    "set_model_context_assembler",
]
