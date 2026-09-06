"""Fact plane package (ADR-0195).

Public production APIs for Session append, event catalog, run bind, fold,
repair, checkpoint, and recovery.
"""

from __future__ import annotations

from lca.session.append import Session
from lca.session.bind import (
    BoundRunEventSession,
    EventSessionBinder,
    RunEventSessionBridge,
    bind_run_event_session,
    bind_run_event_session_from_store,
    event_session_binder_from_scope,
    unbind_run_event_session,
)
from lca.session.catalog import (
    UnknownSessionEventTypeError,
    known_session_event_types,
    validate_event_type_for_read,
)
from lca.session.checkpoint import (
    CheckpointFailure,
    FlushableSession,
    SessionCheckpointPolicy,
    SessionCheckpointPolicyProtocol,
)
from lca.session.fold import (
    REQUEST_HEADER_CATEGORY,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_TOOL_RESULT_TYPE,
    canonicalHeader,
    foldRequestHeader,
    foldSurface,
    headerEquals,
)
from lca.session.recovery import (
    SessionRecoveryError,
    append_approval_resolved_if_pending,
    assert_resume_allowed,
    recover_live_agent,
    recovery_from_events,
    sync_run_status_from_recovery,
)
from lca.session.repair import (
    TOOL_NOT_STARTED,
    TOOL_OUTCOME_UNKNOWN,
    SessionRepairError,
    repair_interrupted_turn,
)

__all__ = [
    "BoundRunEventSession",
    "CheckpointFailure",
    "EventSessionBinder",
    "FlushableSession",
    "REQUEST_HEADER_CATEGORY",
    "RunEventSessionBridge",
    "SURFACE_ASSISTANT_TYPE",
    "SURFACE_TOOL_RESULT_TYPE",
    "Session",
    "SessionCheckpointPolicy",
    "SessionCheckpointPolicyProtocol",
    "SessionRecoveryError",
    "SessionRepairError",
    "TOOL_NOT_STARTED",
    "TOOL_OUTCOME_UNKNOWN",
    "UnknownSessionEventTypeError",
    "append_approval_resolved_if_pending",
    "assert_resume_allowed",
    "bind_run_event_session",
    "bind_run_event_session_from_store",
    "canonicalHeader",
    "event_session_binder_from_scope",
    "foldRequestHeader",
    "foldSurface",
    "headerEquals",
    "known_session_event_types",
    "recover_live_agent",
    "recovery_from_events",
    "repair_interrupted_turn",
    "sync_run_status_from_recovery",
    "unbind_run_event_session",
    "validate_event_type_for_read",
]
