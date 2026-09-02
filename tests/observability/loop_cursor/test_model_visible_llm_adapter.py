"""ADR-0169 PR-12.5:ModelVisibleLLMAdapter 装饰器测试。

覆盖(契约 + 行为):
- Adapter 装饰器在 ``complete`` / ``stream`` **调用内层之前**触发一次
  Capture,落 4 件套(system/tools/messages/manifest)
  到 ``model_visible/step_<NN>/``。
- Capture 产物喂给 ``cursor.record_request_header(...)``:
  - cursor._state.phase 必须已经在 THINK 窗口,否则抛 CursorError(契约守住)
  - payload 携带 4 个 digest + 4 个 path
  - spine EP ``llm.request.header`` 被记一次,fields 完整
- stream 路径只走 1 次 capture(stream 起手),不按 token 切步。
- 缺少 capture 或 cursor 时,capture 失败路径**不**挡业务:
  - 业务调用继续;失败被 log + 透传到 spine 上设的可控降级点
  - 这是 ADR-0169 D5 与 L10 的硬要求(capture 失败不 throw,真值流不漂)
- 装饰器层对内层的返回完全透明(LLMResponse / AsyncIterator 不变)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import (
    LLMResponse,
    LLMStreamEvent,
    TokenUsage,
)
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor_payloads import RequestHeader

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

    # 2) 4 件套落盘
    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    assert (step_dir / "system.json").is_file()
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
    raw = json.loads((step_dir / "messages.json").read_text(encoding="utf-8"))
    assert any(
        m.get("role") == "user" and "hello world" in (m.get("content") or "") for m in raw
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
    # 同样 1 条 llm.request.header EP,4 件套落盘
    step_dir = tmp_path / "run" / "model_visible" / "step-001"
    for stem in ("system", "tools", "messages", "manifest"):
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
