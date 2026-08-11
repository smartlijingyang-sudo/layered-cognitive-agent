"""Projection plane — turn-based SSE projection to OpenAI wire format.

Replaces the monolithic journal_openai_projector with a clean architecture:
    - DiffProjector: diffs TurnSnapshots → SSE chunks
    - Delegates tool lifecycle to ToolProjection (existing)
    - Proper reasoning block boundaries per turn
    - stepCount from TurnSnapshot
    - Run finish forces lifecycle close
"""

from gateway.projection.diff_projector import (
    DiffProjector,
    assert_openai_finish_invariant,
    collect_openai_completion,
    sse_data_lines,
    stream_openai_from_run,
)

__all__ = [
    "DiffProjector",
    "assert_openai_finish_invariant",
    "collect_openai_completion",
    "sse_data_lines",
    "stream_openai_from_run",
]
