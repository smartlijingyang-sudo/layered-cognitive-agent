"""Single LLM turn executor — LobeHub ``call_llm`` / ``callLlmFinalizer`` parity.

One cognitive step = exactly one LLM round-trip. The response (text, tool_calls,
or both) is passed unchanged to ``llm_result`` / ``ModularBrain``.

Forbidden (removed): second completion with ``tool_choice=required`` after a
text-only stream — that broke G2A Mode A and caused search_skill loops.
"""

from __future__ import annotations

import structlog

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.partial_buffer import append_run_partial
from lca.contracts.protocols import LLMAdapter, Tool
from lca.layer1_cognitive.brain.llm_turn.mode import LlmTurnMode
from lca.layer1_cognitive.brain.llm_turn.policy import build_llm_call_kwargs, resolve_llm_turn_mode

_log = structlog.get_logger(__name__)

_EMPTY_STREAM_COMPLETE_RETRIES = 2
_POST_SEARCH_COMPLETE_RETRIES = 3


async def execute_llm_turn(
    llm: LLMAdapter,
    tools: list[Tool],
    prompt: str,
    *,
    step: int,
    state: AgentState,
    task: str = "",
) -> LLMResponse:
    """Run one LobeHub-aligned ``call_llm`` turn."""
    mode = resolve_llm_turn_mode(state)
    llm_kwargs = build_llm_call_kwargs(state=state, task=task)
    if mode == LlmTurnMode.SUMMARIZE:
        return await _summarize_after_search(llm, tools, prompt, step=step, llm_kwargs=llm_kwargs)
    return await _stream_turn(llm, tools, prompt, step=step, llm_kwargs=llm_kwargs)


async def _summarize_after_search(
    llm: LLMAdapter,
    tools: list[Tool],
    prompt: str,
    *,
    step: int,
    llm_kwargs: dict[str, object],
) -> LLMResponse:
    """Stream the post-search summarization so journal emits StepTextDelta / ReasoningDelta."""
    for attempt in range(_POST_SEARCH_COMPLETE_RETRIES):
        accumulated = ""
        stream_response: LLMResponse | None = None
        async for event in llm.stream(prompt, tools=tools, step=step, **llm_kwargs):
            if event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
                chunk = event.text or ""
                accumulated += chunk
                append_run_partial(chunk)
            elif event.type == LLMStreamEventType.COMPLETED and event.response is not None:
                stream_response = event.response
                break

        response = (
            _merge_stream_response(stream_response, accumulated)
            if stream_response is not None
            else LLMResponse(text=accumulated)
            if accumulated.strip()
            else LLMResponse(text="")
        )
        text = (response.text or "").strip()
        if text or response.tool_calls:
            return response
        _log.warning("llm_turn_post_search_empty", step=step, attempt=attempt)
    return LLMResponse(text="")


async def _stream_turn(
    llm: LLMAdapter,
    tools: list[Tool],
    prompt: str,
    *,
    step: int,
    llm_kwargs: dict[str, object],
) -> LLMResponse:
    accumulated = ""
    stream_response: LLMResponse | None = None
    async for event in llm.stream(prompt, tools=tools, step=step, **llm_kwargs):
        if event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
            chunk = event.text or ""
            accumulated += chunk
            append_run_partial(chunk)
        elif event.type == LLMStreamEventType.REASONING_TEXT_DELTA:
            pass
        elif event.type == LLMStreamEventType.COMPLETED and event.response is not None:
            stream_response = event.response
            break

    if stream_response is not None:
        return _merge_stream_response(stream_response, accumulated)

    text = accumulated.strip()
    if text:
        return LLMResponse(text=accumulated)

    for attempt in range(_EMPTY_STREAM_COMPLETE_RETRIES):
        _log.warning("llm_turn_stream_empty_fallback", step=step, attempt=attempt)
        response = await llm.complete(prompt, tools=tools, step=step, **llm_kwargs)
        if response.text or response.tool_calls:
            return response
    return LLMResponse(text="")


def _merge_stream_response(stream_response: LLMResponse, accumulated: str) -> LLMResponse:
    """Prefer provider COMPLETED payload; fill missing text from streamed deltas."""
    if stream_response.tool_calls or (stream_response.text or "").strip():
        return stream_response
    text = accumulated.strip()
    if text:
        return LLMResponse(
            text=accumulated,
            model=stream_response.model,
            tool_calls=stream_response.tool_calls,
            usage=stream_response.usage,
        )
    return stream_response
