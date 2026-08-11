"""Backward-compatible re-export — split into focused modules.

- ``gateway.openai_frame_utils`` — pure helpers (parse, resolve, constants)
- ``gateway.openai_projector`` — ``JournalOpenAiProjector`` state machine
- ``gateway.openai_stream`` — async streaming adapters

This module re-exports everything so existing imports continue to work.
"""

from __future__ import annotations

from gateway.openai_frame_utils import (
    TOOL_RESULT_MAX_LEN,
    USER_FACING_TERMINAL_ACTIONS,
    extract_user_question,
    parse_args_json,
    parse_sse_frame_record,
    resolve_lca_mode,
    safe_json_string,
)
from gateway.openai_projector import (
    JournalOpenAiProjector,
    assert_openai_finish_invariant,
)
from gateway.openai_stream import (
    collect_openai_completion,
    sse_data_lines,
    stream_openai_from_run,
)

__all__ = [
    "JOURNAL_OPENAI_PROJECTOR_DEPRECATED",
    "TOOL_RESULT_MAX_LEN",
    "USER_FACING_TERMINAL_ACTIONS",
    "JournalOpenAiProjector",
    "assert_openai_finish_invariant",
    "collect_openai_completion",
    "extract_user_question",
    "parse_args_json",
    "parse_sse_frame_record",
    "resolve_lca_mode",
    "safe_json_string",
    "sse_data_lines",
    "stream_openai_from_run",
]

JOURNAL_OPENAI_PROJECTOR_DEPRECATED = (
    "gateway.journal_openai_projector is a re-export shim; "
    "import from gateway.openai_projector / gateway.openai_stream directly."
)
