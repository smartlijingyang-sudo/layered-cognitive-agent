"""Backward-compatible re-exports for the refactored stream emitter.

The old ``projection/openai_sse.py`` and ``projection/tool_events.py`` have been
replaced by ``gateway/stream_emitter.py``. This module provides re-exports
for any remaining importers during the transition.
"""

from gateway.stream_emitter import (
    OpenAIStreamEmitter,
    assert_finish_invariant,
    collect_openai_completion,
    stream_openai_chunks,
)

# Backward-compatible aliases
OpenAISSEProjector = OpenAIStreamEmitter
assert_openai_finish_invariant = assert_finish_invariant
stream_openai_from_run = stream_openai_chunks

__all__ = [
    "OpenAISSEProjector",
    "OpenAIStreamEmitter",
    "assert_finish_invariant",
    "assert_openai_finish_invariant",
    "collect_openai_completion",
    "stream_openai_chunks",
    "stream_openai_from_run",
]
