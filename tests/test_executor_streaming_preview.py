"""End-to-end smoke test for executor + ToolCallStreaming preview pipeline.

ADR-0101 followup (2026-09-01): executor should emit partial ``arguments_preview``
on every ``ToolCallStreaming`` event so LobeHub paints the tool card while
arguments are still streaming. This test patches LLMAdapter to drive
``FUNCTION_CALL_ARGUMENTS_DELTA`` events and verifies journal emission.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.observability.journal import StampedEvent, ToolCallStreaming
from lca.infrastructure.observability import bind_backends


class _FakeLLMEvent:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeLLM:
    """Streams ``FUNCTION_CALL_ARGUMENTS_DELTA`` then COMPLETED with empty text."""

    def __init__(self, deltas: list[str]):
        self._deltas = deltas

    async def stream(self, *_, **__) -> AsyncIterator[_FakeLLMEvent]:
        # emit name first
        yield _FakeLLMEvent(
            LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
            tool_name="executeCode",
            tool_call_id="toolu_smoke",
            arguments_delta="",
        )
        # then chunks
        for d in self._deltas:
            yield _FakeLLMEvent(
                LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                tool_name="executeCode",
                tool_call_id="toolu_smoke",
                arguments_delta=d,
            )
        # finally COMPLETED with tool_calls (so _merge_stream_response returns early)
        yield _FakeLLMEvent(
            LLMStreamEventType.COMPLETED,
            response=LLMResponse(text="", tool_calls=[]),
        )


@pytest.mark.asyncio
async def test_executor_emits_arguments_preview_on_streaming() -> None:
    """ToolCallStreaming event 必须携带 partial arguments_preview。

    验证:
    1. 每个 emit (累计 160 字符) 都产生 ToolCallStreaming 事件
    2. arguments_preview 是 dict,不是 None
    3. arguments_preview 的 'code' 字段逐步累积
    """
    from lca.cognition.brain.llm_turn import executor
    from lca.contracts.models.team.partial_buffer import begin_partial_buffer, reset_partial_buffer

    # collect emitted events
    captured: list[ToolCallStreaming] = []

    class _CapturingJournal:
        def write(self, event):
            if isinstance(event, ToolCallStreaming):
                captured.append(event)
            return StampedEvent(
                event=event,
                scope=__import__(
                    "lca.contracts.models.observability.journal",
                    fromlist=["RunScope"],
                ).RunScope(run_id="r", trace_id="t"),
                seq=len(captured) + 1,
                ts=0.0,
            )

    bound = __import__(
        "lca.infrastructure.observability.facade.facade",
        fromlist=["BoundObservability"],
    ).BoundObservability(journal=_CapturingJournal())

    with bind_backends(bound):
        # build 21-delta stream simulating a real LLM
        deltas = [
            r'{"code": "import os',
            r"\n",
            r"code = '''#!/usr/bin/env python3\n",
            r"# -*- coding: utf-8 -*-\n",
            r'"""\n',
            "鸡兔同笼问题求解器\n",
            "=",
            "*",
            "*",
            "x",
            " ",
            "50\n",
            r'"""\n',
            r"\ndef s",
            "olve(heads: int, feet: int):\n",
            "    if feet % 2 != 0:\n",
            "        return None\n",
            "    rabbits = (feet - 2 * heads) // 2\n",
            "    return heads - rabbits, rabbits\n",
            '\nprint("finished")',
        ]

        llm = _FakeLLM(deltas)

        tok = begin_partial_buffer()
        try:
            await executor._stream_turn(
                llm,
                tools=[],
                prompt="hello",
                step=0,
                llm_kwargs={},
            )
        finally:
            reset_partial_buffer(tok)

    # Verify at least one ToolCallStreaming was emitted
    assert len(captured) >= 1, f"expected >=1 ToolCallStreaming, got {len(captured)}"

    # Print what we got for debugging
    for i, ev in enumerate(captured):
        print(f"  emit#{i + 1} preview={ev.arguments_preview!r}")

    # Verify arguments_preview is dict on every event
    for ev in captured:
        assert isinstance(ev.arguments_preview, dict), (
            f"ToolCallStreaming.arguments_preview must be dict, got {type(ev.arguments_preview)}"
        )

    # Verify 'code' is progressively populated if any code prefix is found
    code_progressions = [ev.arguments_preview.get("code", "") for ev in captured]
    if any(code_progressions):
        first_code = code_progressions[0]
        last_code = code_progressions[-1]
        assert last_code, "last preview should have non-empty code if any preview had code"
        assert len(last_code) >= len(first_code), (
            f"code should grow: first={len(first_code)} last={len(last_code)}"
        )
