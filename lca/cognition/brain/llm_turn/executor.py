"""Single LLM turn executor — LobeHub ``call_llm`` / ``callLlmFinalizer`` parity.

One cognitive step = exactly one LLM round-trip. The response (text, tool_calls,
or both) is passed unchanged to ``llm_result`` / ``ModularBrain``.

Forbidden (removed): second completion with ``tool_choice=required`` after a
text-only stream — that broke G2A Mode A and caused search_skill loops.
"""

from __future__ import annotations

import structlog

from lca.cognition.brain.llm_turn.mode import LlmTurnMode
from lca.cognition.brain.llm_turn.policy import build_llm_call_kwargs, resolve_llm_turn_mode
from lca.cognition.brain.tool_call_stream import (
    mark_slot_done,
    parse_completed_slot_args,
    pop_completed_slots,
    push_tool_call_stream,
)
from lca.cognition.brain.tool_conversation import build_tool_history
from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import ToolCallResolved
from lca.contracts.models.team.partial_buffer import append_run_partial
from lca.contracts.protocols import LLMAdapter, Tool
from lca.infrastructure.observability import record

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
    llm_kwargs["history"] = build_tool_history(state)
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
    tool_slots: dict[str, dict[str, object]] = {}
    async for event in llm.stream(prompt, tools=tools, step=step, **llm_kwargs):
        if event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
            chunk = event.text or ""
            accumulated += chunk
            append_run_partial(chunk)
        elif event.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA:
            push_tool_call_stream(
                tool_slots,
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                arguments_delta=event.arguments_delta or "",
            )
        elif event.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DONE:
            if event.tool_call_id:
                mark_slot_done(tool_slots, str(event.tool_call_id))
        elif event.type == LLMStreamEventType.COMPLETED and event.response is not None:
            stream_response = event.response
            break

    # args 收齐才 emit 一次 ToolCallResolved;旧"每 delta 一次 ToolCallStreaming"
    # 是 UI 信号误入事实账本,本批废 (前置步骤 ToolCallStreaming 已被删除)。
    for slot in pop_completed_slots(tool_slots):
        record(
            ToolCallResolved(
                tool_name=str(slot["tool_name"]),
                tool_call_id=str(slot["tool_call_id"]),
                arguments=parse_completed_slot_args(str(slot["raw"])),
            )
        )

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
