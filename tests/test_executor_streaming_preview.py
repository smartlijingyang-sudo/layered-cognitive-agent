"""End-to-end smoke test for executor + ToolCallResolved pipeline.

本批改造 (fix/strip-tool-call-streaming): executor 在 args 收齐那一刻
对每个 tool_call_id emit **恰好一次** ToolCallResolved (载荷完整
arguments dict)。旧"每 delta 一帧 ToolCallStreaming preview"已废 —
journal 是事实流,不是 UI 中间态。

测试 patch LLMAdapter 驱动 ``FUNCTION_CALL_ARGUMENTS_DELTA`` →
``FUNCTION_CALL_ARGUMENTS_DONE`` → ``COMPLETED``,验证:
1. 整个 stream 仅产生 1 个 ToolCallResolved (不是 N 个)
2. 该 Resolved.arguments 是完整 dict,code 字段含整段代码
3. 不再有 ToolCallStreaming 事件落账
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolCallResolved,
)
from lca.infrastructure.observability import bind_backends


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
    """Args 完整时仅 emit 一次 ToolCallResolved,不再有 ToolCallStreaming。"""
    from lca.cognition.brain.llm_turn import executor
    from lca.contracts.models.team.partial_buffer import begin_partial_buffer, reset_partial_buffer

    captured_resolved: list[ToolCallResolved] = []
    captured_all_kinds: list[str] = []

    class _CapturingJournal:
        def write(self, event):
            captured_all_kinds.append(type(event).__name__)
            if isinstance(event, ToolCallResolved):
                captured_resolved.append(event)
            return StampedEvent(
                event=event,
                scope=RunScope(run_id="r", trace_id="t"),
                seq=len(captured_all_kinds),
                ts=0.0,
            )

    bound = __import__(
        "lca.infrastructure.observability.facade.facade",
        fromlist=["BoundObservability"],
    ).BoundObservability(journal=_CapturingJournal())

    with bind_backends(bound):
        # 构造可严格 JSON 解析的 raw —— LLM 把代码内容做 JSON 转义
        # (Python 字符串里的双引号 → \", 三引号 → \"\"\)。
        deltas = [
            r'{"code": "import os\n',
            r"code = \'hello world\'\n",
            r"def solve(heads, feet):\n",
            r"    return heads, feet\n",
            r"\nprint(\'finished\')",
            r'", "language": "python"}',
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

    # 1) 不再 emit 任何 ToolCallStreaming (以及任何其他 ToolCall* 中间态事件)
    streaming_kinds = [
        k
        for k in captured_all_kinds
        if "Streaming" in k or "Streaming" in k.replace("Resolved", "")
    ]
    assert streaming_kinds == [], f"ToolCall*Streaming 已废,不应 emit;got {streaming_kinds}"

    # 2) 恰好 emit 一次 ToolCallResolved
    assert len(captured_resolved) == 1, (
        f"expected exactly 1 ToolCallResolved per tool_call, got {len(captured_resolved)}"
    )

    resolved = captured_resolved[0]
    assert resolved.tool_name == "executeCode"
    assert resolved.tool_call_id == "toolu_smoke"

    # 3) arguments 完整: code 字段含整段代码(包含 'finished')
    args = resolved.arguments
    assert isinstance(args, dict)
    code = args.get("code") or ""
    assert "finished" in code, (
        f"Resolved.arguments.code must contain full code, got tail={code[-80:]!r}"
    )
