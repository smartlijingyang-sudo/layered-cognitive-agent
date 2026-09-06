"""End-to-end smoke test for executor + ToolCallResolved pipeline.

本批改造 (fix/strip-tool-call-streaming): executor 在 args 收齐那一刻
对每个 tool_call_id commit **恰好一次** ``tool.call.resolved.v1`` (载荷完整
arguments dict)。旧"每 delta 一帧 ToolCallStreaming preview"已废 —
journal 是事实流,不是 UI 中间态。

测试 patch LLMAdapter 驱动 ``FUNCTION_CALL_ARGUMENTS_DELTA`` →
``FUNCTION_CALL_ARGUMENTS_DONE`` → ``COMPLETED``,验证:
1. 整个 stream 仅产生 1 个 tool.call.resolved.v1 (不是 N 个)
2. 该 event 的 arguments 是完整 dict,code 字段含整段代码
3. 不再有 ToolCallStreaming 事件落账
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


class _FakeLLMEvent:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeLLM:
    """Streams ``FUNCTION_CALL_ARGUMENTS_DELTA`` chunks then DONE then COMPLETED."""

    def __init__(self, deltas: list[str], tool_call_id: str = "toolu_smoke"):
        self._deltas = deltas
        self._tool_call_id = tool_call_id

    async def stream(self, *_, **__) -> AsyncIterator[_FakeLLMEvent]:
        yield _FakeLLMEvent(
            LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
            tool_name="executeCode",
            tool_call_id=self._tool_call_id,
            arguments_delta="",
        )
        for d in self._deltas:
            yield _FakeLLMEvent(
                LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                tool_name="executeCode",
                tool_call_id=self._tool_call_id,
                arguments_delta=d,
            )
        yield _FakeLLMEvent(
            LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DONE,
            tool_name="executeCode",
            tool_call_id=self._tool_call_id,
        )
        yield _FakeLLMEvent(
            LLMStreamEventType.COMPLETED,
            response=LLMResponse(text="", tool_calls=[]),
        )


@pytest.mark.asyncio
async def test_executor_emits_exactly_one_resolved_per_tool_call() -> None:
    """Args 完整时仅 commit 一次 tool.call.resolved.v1,不再有 ToolCallStreaming。"""
    from lca.cognition.brain.llm_turn import executor
    from lca.contracts.models.team.partial.buffer import begin_partial_buffer, reset_partial_buffer

    session = Session("r-smoke")
    token = set_publish_session(session)
    try:
        deltas = [
            r'{"code": "import os\n',
            r"code = \'hello world\'\n",
            r"def solve(heads, feet):\n",
            r"    return heads, feet\n",
            r"\nprint(\'finished\')",
            r'", "language": "python"}',
        ]

        llm = _FakeLLM(deltas)

        partial_token = begin_partial_buffer()
        try:
            await executor._stream_turn(
                llm,
                tools=[],
                prompt="hello",
                step=0,
                llm_kwargs={},
            )
        finally:
            reset_partial_buffer(partial_token)

        assert session.event_count == 1, (
            f"expected exactly 1 tool.call.resolved.v1 per tool_call, got {session.event_count}"
        )
        event = session.event_at(0)
        assert event is not None
        assert event.type == "tool.call.resolved.v1"
        assert event.actor == "brain"
        assert event.data["tool_name"] == "executeCode"
        assert event.data["tool_call_id"] == "toolu_smoke"

        args = event.data["arguments"]
        assert isinstance(args, dict)
        code = args.get("code") or ""
        assert "finished" in code, (
            f"Resolved.arguments.code must contain full code, got tail={code[-80:]!r}"
        )
    finally:
        reset_publish_session(token)
