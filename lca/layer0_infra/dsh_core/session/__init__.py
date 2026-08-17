"""1:1 port of ``@deepseek-ai/dsh-session``.

Event-sourced session service: append-only session log, in-memory store,
and the derived LLM message history.
"""

from __future__ import annotations

# Chunk rows
from lca.layer0_infra.dsh_core.session.chunk_rows import (
    ChunkRow,
    StorageRecord,
    decode_storage_record,
    pack_chunk_runs,
)

# Index (Session, SessionStore)
from lca.layer0_infra.dsh_core.session.index import (
    Session,
    SessionForkError,
    SessionStore,
    adopt_session_event,
    snapshot_session_event,
)

# JSON utilities
from lca.layer0_infra.dsh_core.session.json_ import (
    JsonValue,
    is_json_value,
    snapshot_json_value,
)

# Known event types
from lca.layer0_infra.dsh_core.session.known_event_types import (
    KNOWN_SESSION_EVENT_TYPES,
)

# Preparation
from lca.layer0_infra.dsh_core.session.preparation import (
    SessionPreparation,
)

# Repair
from lca.layer0_infra.dsh_core.session.repair import (
    TOOL_NOT_STARTED,
    TOOL_OUTCOME_UNKNOWN,
    interrupted_turn_closers,
)

# Request header
from lca.layer0_infra.dsh_core.session.request_header import (
    canonical_header,
    fold_request_header,
    header_equals,
)

# Surface
from lca.layer0_infra.dsh_core.session.surface import (
    SessionSurface,
    SurfaceFoldReplacement,
    SurfaceFoldResult,
    SurfaceManager,
    derive_event_message,
    fold_surface,
    is_append_surface_event,
    is_replacement_surface_event,
    is_surface_eligible_type,
    is_surface_event,
)

# Core types
from lca.layer0_infra.dsh_core.session.types import (
    SESSION_FORMAT_VERSION,
    CreateSessionOptions,
    EpochHeader,
    PrepareSessionOptions,
    ReplaceSurfaceOp,
    RequestContext,
    RestoredSessionOptions,
    SessionEvent,
    SessionHeader,
    SessionId,
    SurfaceIntent,
    TodoItem,
)

__all__ = [
    "KNOWN_SESSION_EVENT_TYPES",
    "SESSION_FORMAT_VERSION",
    "TOOL_NOT_STARTED",
    "TOOL_OUTCOME_UNKNOWN",
    "ChunkRow",
    "CreateSessionOptions",
    "EpochHeader",
    "JsonValue",
    "PrepareSessionOptions",
    "ReplaceSurfaceOp",
    "RequestContext",
    "RestoredSessionOptions",
    "Session",
    "SessionEvent",
    "SessionForkError",
    "SessionHeader",
    "SessionId",
    "SessionPreparation",
    "SessionStore",
    "SessionSurface",
    "StorageRecord",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "SurfaceIntent",
    "TodoItem",
    "adopt_session_event",
    "canonical_header",
    "decode_storage_record",
    "derive_event_message",
    "fold_request_header",
    "fold_surface",
    "header_equals",
    "interrupted_turn_closers",
    "is_append_surface_event",
    "is_json_value",
    "is_replacement_surface_event",
    "is_surface_eligible_type",
    "is_surface_event",
    "pack_chunk_runs",
    "snapshot_json_value",
    "snapshot_session_event",
]
