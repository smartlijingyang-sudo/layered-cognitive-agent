"""SSE output layer — journal events → OpenAI wire format.

OpenAISSEProjector: direct event-to-chunk mapping, no indirection.
ToolEventProjector: tool lifecycle → LCA extension events.
"""

from gateway.projection.openai_sse import (
    OpenAISSEProjector,
    assert_openai_finish_invariant,
    collect_openai_completion,
    sse_data_lines,
    stream_openai_from_run,
)

__all__ = [
    "OpenAISSEProjector",
    "assert_openai_finish_invariant",
    "collect_openai_completion",
    "sse_data_lines",
    "stream_openai_from_run",
]
