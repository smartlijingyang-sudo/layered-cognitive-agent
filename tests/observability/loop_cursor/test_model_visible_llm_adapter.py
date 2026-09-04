"""ADR-0169 PR-12.5:ModelVisibleLLMAdapter 装饰器测试。

覆盖(契约 + 行为):
- Adapter 装饰器在 ``complete`` / ``stream`` **调用内层之前**触发一次
  Capture,落 4 件套(system/tools/messages/manifest)
  到 ``model_visible/step_<NN>/``。
- Capture 产物喂给 ``cursor.record_request_header(...)``:
  - cursor._state.phase 必须已经在 THINK 窗口,否则抛 CursorError(契约守住)
  - payload 携带 4 个 digest + 4 个 path
  - spine EP ``llm.request.header`` 被记一次,fields 完整
  - ``request-header.json`` 持久化到 step 目录(同字段集)
- 内层返回最终响应后落 ``thinking.json`` + ``step.thinking.record`` EP
  (thinking_kind=final_response,text_preview 截断 ≤ 2000 字符);
  complete / stream(COMPLETED 事件)各记 1 次。
- Reasoner 绑定 ``CurrentReasonerPrompt``(携带 PromptTrace + ContextManifest)
  时:``context-manifest.json`` 落盘,携带 skill ids + section trace +
  context items;RequestHeader.manifest_digest/path 指向该文件;
  未绑定时保留降级 manifest,不写 context-manifest.json。
- stream 路径只走 1 次 capture(stream 起手),不按 token 切步。
- 缺少 capture 或 cursor 时,capture 失败路径**不**挡业务:
  - 业务调用继续;失败被 log + 透传到 spine 上设的可控降级点
  - 这是 ADR-0169 D5 与 L10 的硬要求(capture 失败不 throw,真值流不漂)
- 装饰器层对内层的返回完全透明(LLMResponse / AsyncIterator 不变)
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import (
    LLMResponse,
    LLMStreamEvent,
    NativeToolCall,
    TokenUsage,
)
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import LoopCursor
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
)

# 接下来要写:ModelVisibleLLMAdapter(本测试是 TDD 先行)
from lca.infrastructure.observability.adapters.model_visible_llm_adapter import (
    ModelVisibleLLMAdapter,
)
from lca.infrastructure.observability.loop_cursor import (
    InMemoryLoopCursor,
    StdModelVisibleCapture,
)


class _FakeLLMAdapter:
    name = "fake-llm"

    def __init__(
        self,
        *,
        complete_response: LLMResponse | None = None,
        stream_events: list[LLMStreamEvent] | None = None,
    ) -> None:
        self._complete_response = complete_response or LLMResponse(
            text="hello",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=2, completion_tokens=3),
            finish_reason="stop",
        )
        self._stream_events = stream_events or []

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.prompt_seen = prompt
        self.kwargs_seen = kwargs
        return self._complete_response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        self.prompt_seen = prompt
        self.kwargs_seen = kwargs
        for event in self._stream_events:
            yield event


def _install_cursor_and_capture(
    *,
    tmp_path: Path,
    spine_capture: list[tuple[str, dict]],
) -> tuple[InMemoryLoopCursor, StdModelVisibleCapture]:
    """构造 cursor + capture,cursor spine 写入到 spine_capture 列表便于断言。"""

    class _ListSpine:
        def append(self, **kw: Any) -> int:
            spine_capture.append((kw["execution_point"], kw.get("payload", {})))
            return len(spine_capture)

    cursor = InMemoryLoopCursor(
        run_id="r-test",
        trace_id="t-test",
        incarnation=Incarnation(run_id="r-test", plan_ref="default", incarnation_seq=1),
        spine=_ListSpine(),
    )
    # Advance to THINK — record_request_header 必须 THINK 窗口
    cursor.advance("perceive")
    cursor.advance("think")
    capture = StdModelVisibleCapture(run_dir=tmp_path / "run")
    return cursor, capture


class _RecordingCursor:
    """LoopCursor 测试替身:委托 InMemoryLoopCursor,额外记录 record_thinking 调用。

    记录形态:``(ThinkingRecord payload, text_preview)`` 元组序列,供断言
    record_thinking 的关键字参数(含 text_preview)。
    """

    def __init__(self, inner: InMemoryLoopCursor) -> None:
        self._inner = inner
        self.thinking_calls: list[tuple[ThinkingRecord, str]] = []

    @property
    def snapshot(self) -> Any:
        return self._inner.snapshot

    def advance(self, phase: Any, **kwargs: Any) -> Any:
        return self._inner.advance(phase, **kwargs)

    def halt(self, reason: Any) -> None:
        self._inner.halt(reason)

    def close(self, reason: Any) -> None:
        self._inner.close(reason)

    def record_thinking(self, payload: ThinkingRecord, *, text_preview: str = "") -> None:
        self.thinking_calls.append((payload, text_preview))
        self._inner.record_thinking(payload, text_preview=text_preview)

    def record_tool_call(self, payload: Any, **kwargs: Any) -> None:
        self._inner.record_tool_call(payload, **kwargs)

    def record_tool_result(self, payload: Any, **kwargs: Any) -> None:
        self._inner.record_tool_result(payload, **kwargs)

    def record_request_header(self, header: Any) -> None:
        self._inner.record_request_header(header)

    def fork(self, reason: Any) -> LoopCursor:
        return self._inner.fork(reason)


def _replay_sha256(data: Any) -> str:
    """replay cursor 同口径的 canonical sha256(JSON sort_keys + ensure_ascii=False)。"""
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


@pytest.mark.asyncio
async def test_complete_writes_four_model_visible_files(
    tmp_path: Path,
) -> None:
    """Adapter 装饰器完整路径:落 4 件套 + 1 条 llm.request.header EP。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake-model")

    response = await adapter.complete("hello world")

    # 1) 内层被调用并透传返回
    assert response.text == "hello"
    assert inner.prompt_seen == "hello world"

    # 2) ADR-0176 D4:3 件套(system.json 删除,system 数据并入 messages.json)
    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    assert not (step_dir / "system.json").exists()
    assert (step_dir / "tools.json").is_file()
    assert (step_dir / "messages.json").is_file()
    assert (step_dir / "manifest.json").is_file()
    # inherited 默认不创建
    assert not (step_dir / "inherited.json").exists()

    # 3) spine 上有 1 条 llm.request.header
    ep_names = [name for name, _ in spine_calls]
    assert "llm.request.header" in ep_names
    assert len([e for e in ep_names if e == "llm.request.header"]) == 1

    # 4) 该 EP 携带 4 digest + 4 path
    (_, payload) = next((n, p) for n, p in spine_calls if n == "llm.request.header")
    for field in (
        "system_digest",
        "tools_digest",
        "messages_digest",
        "manifest_digest",
        "system_path",
        "tools_path",
        "messages_path",
        "manifest_path",
        "model",
        "reason",
        "step_id",
        "incarnation",
    ):
        assert field in payload, f"missing field {field!r} in payload"
    # digest 前缀
    for d in (
        payload["system_digest"],
        payload["tools_digest"],
        payload["messages_digest"],
        payload["manifest_digest"],
    ):
        assert d.startswith("sha256:")

    # 5) messages.json 至少包含 user 消息(由 prompt 派生)
    # ADR-0176 D4:messages.json 现在是 dict 结构,包含 messages_overview.system + messages。
    raw = json.loads((step_dir / "messages.json").read_text(encoding="utf-8"))
    msgs = raw.get("messages", []) if isinstance(raw, dict) else raw
    assert any(
        m.get("role") == "user" and "hello world" in (m.get("content") or "") for m in msgs
    ), raw


@pytest.mark.asyncio
async def test_stream_writes_one_set_of_files(tmp_path: Path) -> None:
    """stream 路径只走 1 次 capture(起手),不按 token 切步。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    inner = _FakeLLMAdapter(
        stream_events=[
            LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="H"),
            LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="i"),
            LLMStreamEvent(
                type=LLMStreamEventType.COMPLETED,
                response=LLMResponse(
                    text="Hi",
                    model="fake-model",
                    usage=TokenUsage(prompt_tokens=1, completion_tokens=2),
                    finish_reason="stop",
                ),
            ),
        ]
    )
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake-model")

    chunks: list[str] = []
    async for event in adapter.stream("prompt for stream"):
        if event.type == LLMStreamEventType.OUTPUT_TEXT_DELTA:
            chunks.append(event.text or "")

    assert "".join(chunks) == "Hi"
    # 同样 1 条 llm.request.header EP,3 件套落盘(ADR-0176 D4:system.json 删除)
    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    assert not (step_dir / "system.json").exists()
    for stem in ("tools", "messages", "manifest"):
        assert (step_dir / f"{stem}.json").is_file(), stem

    ep_names = [n for n, _ in spine_calls]
    assert len([e for e in ep_names if e == "llm.request.header"]) == 1


@pytest.mark.asyncio
async def test_adapter_propagates_inner_runtime_error(tmp_path: Path) -> None:
    """inner 抛异常时,capture 仍然在前面跑过(spine 上仍有 1 条 EP),异常被透传。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)

    class _BoomLLM:
        name = "boom"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            raise RuntimeError("provider offline")

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            raise RuntimeError("provider offline")
            yield  # pragma: no cover

    adapter = ModelVisibleLLMAdapter(_BoomLLM(), cursor=cursor, capture=capture, model="boom")
    with pytest.raises(RuntimeError, match="provider offline"):
        await adapter.complete("hi")

    # 异常路径:依然在调内层之前完成 capture + record_request_header(spine 1 条)
    assert any(n == "llm.request.header" for n, _ in spine_calls)


@pytest.mark.asyncio
async def test_adapter_without_cursor_still_calls_inner(tmp_path: Path) -> None:
    """cursor=None 时:装饰器透明透传 — 不写盘、不落 EP、业务继续。

    Adapter 契约:cursor + capture 是同一个观测 seam,缺一就不走 capture。
    测试验证:业务 response 拿到;不抛;不落盘。
    """
    capture = StdModelVisibleCapture(run_dir=tmp_path / "run")
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=None, capture=capture, model="fake-model")

    response = await adapter.complete("hi")
    assert response.text == "hello"

    # 不写盘:cursor 缺失 ⇒ 透明分支
    step_dir = tmp_path / "run" / "model_visible"
    assert not step_dir.exists()


@pytest.mark.asyncio
async def test_adapter_without_capture_still_calls_inner(tmp_path: Path) -> None:
    """capture=None 时:装饰器透明透传(spine EP 0 条),不抛。

    允许 profile 显式关闭 model_visible capture(例如无 disk profile)。
    """
    spine_calls: list[tuple[str, dict]] = []
    cursor, _ = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)

    class _RecordingSpine:
        def append(self, **kw: Any) -> int:
            spine_calls.append((kw["execution_point"], kw.get("payload", {})))
            return len(spine_calls)

    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=None, model="fake-model")

    response = await adapter.complete("hi")
    assert response.text == "hello"
    # 未落 llm.request.header 因 capture 缺席
    assert not any(n == "llm.request.header" for n, _ in spine_calls)


def test_model_visible_llm_adapter_satisfies_protocol(tmp_path: Path) -> None:
    """Adapter 满足 LLMAdapter Protocol(duck-type)。"""
    from lca.contracts.protocols.runtime.infra import LLMAdapter

    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=None, capture=None, model="x")
    assert isinstance(adapter, LLMAdapter)


def test_request_header_step_id_uses_cursor_step_index(tmp_path: Path) -> None:
    """step_id 由 cursor.snapshot 派生;不是由 adapter 输入。"""
    cursor, _capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=[])

    # 手工走到一个非 1 的 step
    cursor.advance("perceive")
    cursor.advance("think")
    # 调 record_request_header 一次(step_index 已 1)
    cursor.record_request_header(
        RequestHeader(
            step_id="step-001",
            incarnation=1,
            reason="initial",
            model="x",
            system_digest="sha256:a",
            system_path="s",
            tools_digest="sha256:b",
            tools_path="t",
            messages_digest="sha256:c",
            messages_path="m",
            manifest_digest="sha256:d",
            manifest_path="M",
        )
    )
    snap = cursor.snapshot
    assert snap.step_id == "step-001"


@pytest.mark.asyncio
async def test_adapter_self_advances_to_think_when_phase_none(
    tmp_path: Path,
) -> None:
    """Adapter 在 cursor phase=None 时主动 advance('think') 打开 RECORD 窗口。

    生产路径上 cognitive driver (perceive_hub 等) 在 PR-26 阶段仍未调
    cursor.advance('think') 双写;Adapter 必须自检 phase,否则 record_request_header
    会被 CursorError 跳过(PR-12.5 已 catch 但不落 EP)。
    """
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    # 退回到 phase=None 模拟生产真实状态
    while cursor.snapshot.phase is not None and cursor.snapshot.phase != "stop":
        # 用 close 然后再构造一个新的 phase=None cursor
        break  # pragma: no cover — 不走本路径;测试改用显式干净 cursor

    # 干净起见:构造初始 phase=None 的 cursor
    class _LocalSpine:
        def append(self, **kw: Any) -> int:
            spine_calls.append((kw["execution_point"], kw.get("payload", {})))
            return len(spine_calls)

    cursor = InMemoryLoopCursor(
        run_id="r2",
        trace_id="t2",
        incarnation=Incarnation(run_id="r2", plan_ref="default", incarnation_seq=1),
        spine=_LocalSpine(),
    )
    capture = StdModelVisibleCapture(run_dir=tmp_path / "run2")
    assert cursor.snapshot.phase is None

    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake")
    await adapter.complete("hi")

    # cursor 应走到 think,且 spine 派生 phase.think.fold + llm.request.header
    assert cursor.snapshot.phase == "think"
    ep_names = [n for n, _ in spine_calls]
    assert "phase.think.fold" in ep_names, ep_names
    assert "llm.request.header" in ep_names, ep_names
    # 4 件套落盘
    step_dir = tmp_path / "run2" / "model_visible" / "step-001"
    assert (step_dir / "messages.json").is_file()


@pytest.mark.asyncio
async def test_adapter_does_not_re_advance_when_already_thinking(
    tmp_path: Path,
) -> None:
    """phase 已经 think 时,Adapter 不重复 advance — 防 ``phase.think.fold`` EP 翻倍。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake")
    # _install_cursor_and_capture 已经把 cursor 推到 THINK
    await adapter.complete("hi")

    think_fold_count = sum(1 for n, p in spine_calls if n == "phase.think.fold")
    # cursor 提前 advance 了 perceive→think(2 次 phase.think.fold)+ Adapter no-op = 1
    assert think_fold_count == 1, spine_calls
    # llm.request.header 应该 1 次
    assert sum(1 for n, _ in spine_calls if n == "llm.request.header") == 1


@pytest.mark.asyncio
async def test_adapter_skips_record_when_cursor_closed(
    tmp_path: Path,
) -> None:
    """cursor 已 closed ⇒ record / advance 都不动;业务调用继续完成。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    cursor.close("completed")  # phase=None,closed=True
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake")

    # 业务调用继续完成
    response = await adapter.complete("hi")
    assert response.text == "hello"
    # 关闭后不走 capture / record(走透明)
    llm_request_count = sum(1 for n, _ in spine_calls if n == "llm.request.header")
    assert llm_request_count == 0
    # 也不写盘(cursor 已关)
    step_dir = tmp_path / "run" / "model_visible"
    assert not step_dir.exists()


# ── thinking 落盘 + step.thinking.record EP(ADR-0167 D4) ────────────────


@pytest.mark.asyncio
async def test_complete_writes_thinking_json_and_records_thinking(
    tmp_path: Path,
) -> None:
    """complete() 返回后:thinking.json 落 step 目录 + 1 条 step.thinking.record EP。

    record_thinking 携带 ThinkingRecord(digest/path/token_count/kind)与
    关键字参数 text_preview(≤ 2000 字符前缀)。
    """
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    recording = _RecordingCursor(cursor)
    inner = _FakeLLMAdapter()  # text="hello", completion_tokens=3
    adapter = ModelVisibleLLMAdapter(inner, cursor=recording, capture=capture, model="fake-model")

    await adapter.complete("hello world")

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    thinking_path = step_dir / "thinking.json"
    assert thinking_path.is_file()
    payload = json.loads(thinking_path.read_text(encoding="utf-8"))
    assert payload["thinking_kind"] == "final_response"
    assert payload["step_id"] == "step-001"
    assert payload["text"] == "hello"

    assert len(recording.thinking_calls) == 1
    record, preview = recording.thinking_calls[0]
    assert record.thinking_kind == "final_response"
    assert record.content_digest.startswith("sha256:")
    assert record.content_digest == _replay_sha256(payload)
    assert record.content_path == "model_visible/step-001/thinking.json"
    assert record.token_count == 3
    assert preview == "hello"

    thinking_eps = [p for n, p in spine_calls if n == "step.thinking.record"]
    assert len(thinking_eps) == 1
    assert thinking_eps[0]["text_preview"] == "hello"
    assert thinking_eps[0]["thinking_kind"] == "final_response"


@pytest.mark.asyncio
async def test_complete_truncates_text_preview_to_2000_chars(tmp_path: Path) -> None:
    """text_preview 只携带前 2000 字符;thinking.json 保留全文。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    recording = _RecordingCursor(cursor)
    long_text = "x" * 5000
    inner = _FakeLLMAdapter(
        complete_response=LLMResponse(
            text=long_text,
            model="fake-model",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=9),
            finish_reason="stop",
        )
    )
    adapter = ModelVisibleLLMAdapter(inner, cursor=recording, capture=capture, model="fake-model")

    await adapter.complete("prompt")

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    payload = json.loads((step_dir / "thinking.json").read_text(encoding="utf-8"))
    assert payload["text"] == long_text  # sidecar 保留全文
    record, preview = recording.thinking_calls[0]
    assert preview == "x" * 2000
    assert record.token_count == 9


@pytest.mark.asyncio
async def test_thinking_records_tool_calls_summary_when_text_empty(
    tmp_path: Path,
) -> None:
    """text 为空且有 tool_calls 时:thinking.json 落 tool_calls 摘要。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    recording = _RecordingCursor(cursor)
    inner = _FakeLLMAdapter(
        complete_response=LLMResponse(
            text="",
            model="fake-model",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=2),
            finish_reason="tool_calls",
            tool_calls=[
                NativeToolCall(call_id="call-1", name="search", arguments={"q": "weather"}),
            ],
        )
    )
    adapter = ModelVisibleLLMAdapter(inner, cursor=recording, capture=capture, model="fake-model")

    await adapter.complete("prompt")

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    payload = json.loads((step_dir / "thinking.json").read_text(encoding="utf-8"))
    assert payload["text"] == ""
    summary = payload["tool_calls_summary"]
    assert summary[0]["call_id"] == "call-1"
    assert summary[0]["name"] == "search"
    assert summary[0]["arguments_digest"].startswith("sha256:")
    assert len(recording.thinking_calls) == 1


@pytest.mark.asyncio
async def test_stream_records_thinking_once_on_completed(tmp_path: Path) -> None:
    """stream 路径:COMPLETED 事件携带最终响应 → thinking 记 1 次,不按 delta 记。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    recording = _RecordingCursor(cursor)
    inner = _FakeLLMAdapter(
        stream_events=[
            LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="H"),
            LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="i"),
            LLMStreamEvent(
                type=LLMStreamEventType.COMPLETED,
                response=LLMResponse(
                    text="Hi",
                    model="fake-model",
                    usage=TokenUsage(prompt_tokens=1, completion_tokens=2),
                    finish_reason="stop",
                ),
            ),
        ]
    )
    adapter = ModelVisibleLLMAdapter(inner, cursor=recording, capture=capture, model="fake-model")

    async for _event in adapter.stream("prompt for stream"):
        pass

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    payload = json.loads((step_dir / "thinking.json").read_text(encoding="utf-8"))
    assert payload["text"] == "Hi"
    assert len(recording.thinking_calls) == 1
    _record, preview = recording.thinking_calls[0]
    assert preview == "Hi"
    assert sum(1 for n, _ in spine_calls if n == "step.thinking.record") == 1


@pytest.mark.asyncio
async def test_no_thinking_record_when_inner_raises(tmp_path: Path) -> None:
    """内层抛异常:无最终响应 ⇒ 不落 thinking,异常照常透传。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    recording = _RecordingCursor(cursor)

    class _BoomLLM:
        name = "boom"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            raise RuntimeError("provider offline")

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            raise RuntimeError("provider offline")
            yield  # pragma: no cover

    adapter = ModelVisibleLLMAdapter(_BoomLLM(), cursor=recording, capture=capture, model="boom")
    with pytest.raises(RuntimeError, match="provider offline"):
        await adapter.complete("hi")

    assert recording.thinking_calls == []
    assert not (tmp_path / "run" / "model_visible" / "step-001" / "thinking.json").exists()


# ── context-manifest.json + request-header.json(ADR-0167 D3/D4) ─────────


def _bind_prompt_with_trace():
    """绑定携带 PromptTrace + ContextManifest 的 CurrentReasonerPrompt;返回 reset token。"""
    from lca.contracts.models.cognition.prompt_assembly import (
        PromptTrace,
        SectionTrace,
    )
    from lca.contracts.models.core.perception import ContextItem, ContextManifest
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        CurrentReasonerPrompt,
        bind_current_reasoner_prompt,
    )

    trace = PromptTrace(
        template_id="react_prompt",
        variant="react",
        selector_decision_path="profile_default",
        sections=(
            SectionTrace(
                name="role",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=5,
                text="hello",
            ),
            SectionTrace(
                name="context",
                kind="stateful",
                optional=True,
                used_fallback=True,
                skipped_empty=False,
                text_chars=0,
                text="",
            ),
        ),
        total_chars=5,
        activated_skill_ids=("skill.web_search", "skill.memory"),
        tools_count=2,
        available_skills_count=3,
        system_prompt_text="RENDERED SYSTEM PROMPT",
    )
    context_manifest = ContextManifest(
        items=(
            ContextItem(kind="clock", payload="2026-09-04 12:00", provenance="clock_sensor"),
            ContextItem(
                kind="memory",
                payload={"fact": "user prefers concise answers", "score": 0.9},
                provenance="memory_sensor",
            ),
        )
    )
    return bind_current_reasoner_prompt(
        CurrentReasonerPrompt(
            step_id="step-001",
            template_id=trace.template_id,
            selector_decision_path=trace.selector_decision_path,
            system_prompt_text=trace.system_prompt_text,
            prompt_trace=trace,
            context_manifest=context_manifest,
        )
    )


@pytest.mark.asyncio
async def test_bound_prompt_trace_writes_context_manifest(tmp_path: Path) -> None:
    """绑定 PromptTrace + ContextManifest 时:

    - context-manifest.json 落盘,携带 skill ids / section trace / context items
      (section 只落 name + text_chars + digest + fallback 标记,不落全文)
    - manifest.json body 同真值(不再是降级 dict)
    - RequestHeader.manifest_digest/path 指向 context-manifest.json,
      digest 与 replay cursor canonical sha256 对位
    """
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        reset_current_reasoner_prompt,
    )

    token = _bind_prompt_with_trace()
    try:
        spine_calls: list[tuple[str, dict]] = []
        cursor, capture = _install_cursor_and_capture(
            tmp_path=tmp_path, spine_capture=spine_calls
        )
        inner = _FakeLLMAdapter()
        adapter = ModelVisibleLLMAdapter(
            inner, cursor=cursor, capture=capture, model="fake-model"
        )
        await adapter.complete("hello world")
    finally:
        reset_current_reasoner_prompt(token)

    step_dir = tmp_path / "run" / "model_visible" / "step-001"

    # 1) context-manifest.json:skill / section 装配可重建
    ctx_doc = json.loads((step_dir / "context-manifest.json").read_text(encoding="utf-8"))
    assert ctx_doc["source"] == "model_visible_llm_adapter"
    assert ctx_doc["template_id"] == "react_prompt"
    assert ctx_doc["selector_decision_path"] == "profile_default"
    assert ctx_doc["activated_skill_ids"] == ["skill.web_search", "skill.memory"]
    assert ctx_doc["tools_count"] == 2
    assert ctx_doc["available_skills_count"] == 3
    sections = ctx_doc["sections"]
    assert [s["name"] for s in sections] == ["role", "context"]
    assert sections[0]["text_chars"] == 5
    assert sections[0]["content_digest"].startswith("sha256:")
    assert sections[0]["skipped_empty"] is False
    assert sections[0]["used_fallback"] is False
    # section 全文不进 context-manifest(已在 system_prompt_sections.json)
    assert "text" not in sections[0]
    # 空 section:digest 为 None,fallback 标记保留
    assert sections[1]["content_digest"] is None
    assert sections[1]["used_fallback"] is True
    # context items:kind + payload 预览
    items = ctx_doc["context_manifest_items"]
    assert items[0] == {"kind": "clock", "payload_preview": "2026-09-04 12:00"}
    assert items[1]["kind"] == "memory"
    assert "user prefers concise answers" in items[1]["payload_preview"]

    # 2) manifest.json body 同真值
    manifest_doc = json.loads((step_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_doc["body"]["activated_skill_ids"] == ["skill.web_search", "skill.memory"]
    assert manifest_doc["body"]["template_id"] == "react_prompt"

    # 3) llm.request.header EP 指向 context-manifest.json 且 digest 可离线对位
    (_, header_payload) = next(
        (n, p) for n, p in spine_calls if n == "llm.request.header"
    )
    assert header_payload["manifest_path"] == "model_visible/step-001/context-manifest.json"
    assert header_payload["manifest_digest"] == _replay_sha256(ctx_doc)


@pytest.mark.asyncio
async def test_request_header_json_persisted_with_fields(tmp_path: Path) -> None:
    """request-header.json 持久化到 step 目录,字段集供 replay cursor 对位。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake-model")

    await adapter.complete("hello world")

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    header_doc = json.loads((step_dir / "request-header.json").read_text(encoding="utf-8"))
    assert header_doc["step_id"] == "step-001"
    assert header_doc["reason"] == "initial"
    assert header_doc["model"] == "fake-model"
    assert header_doc["inherited_from_step"] is None
    for field_name in (
        "system_digest",
        "system_path",
        "tools_digest",
        "tools_path",
        "messages_digest",
        "messages_path",
        "manifest_digest",
        "manifest_path",
    ):
        assert field_name in header_doc, f"missing {field_name!r}"
    # 未绑定 reasoner prompt ⇒ manifest 指向 manifest.json(无 context-manifest.json)
    assert header_doc["manifest_path"] == "model_visible/step-001/manifest.json"
    assert not (step_dir / "context-manifest.json").exists()
    # digest 与落盘文件对位(同 replay cursor canonical 口径)
    manifest_doc = json.loads((step_dir / "manifest.json").read_text(encoding="utf-8"))
    assert header_doc["manifest_digest"] == _replay_sha256(manifest_doc)
    messages_doc = json.loads((step_dir / "messages.json").read_text(encoding="utf-8"))
    assert header_doc["messages_digest"] == _replay_sha256(messages_doc)


@pytest.mark.asyncio
async def test_degraded_manifest_fallback_when_nothing_bound(tmp_path: Path) -> None:
    """无绑定时:降级 manifest 原样保留;不写 context-manifest.json。"""
    spine_calls: list[tuple[str, dict]] = []
    cursor, capture = _install_cursor_and_capture(tmp_path=tmp_path, spine_capture=spine_calls)
    inner = _FakeLLMAdapter()
    adapter = ModelVisibleLLMAdapter(inner, cursor=cursor, capture=capture, model="fake-model")

    await adapter.complete("hello world", temperature=0.2)

    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    assert not (step_dir / "context-manifest.json").exists()
    manifest_doc = json.loads((step_dir / "manifest.json").read_text(encoding="utf-8"))
    body = manifest_doc["body"]
    assert body["source"] == "model_visible_llm_adapter"
    assert body["prompt_chars"] == len("hello world")
    assert body["has_tools"] is False
    assert body["has_temperature"] is True
    assert body["kwargs_keys"] == ["temperature"]
    assert "template_id" not in body
    assert "activated_skill_ids" not in body
    assert "context_manifest_items" not in body
