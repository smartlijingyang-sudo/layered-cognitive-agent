"""ADR-0169 PR-12.6/12.7: 集成测试 — LLM Adapter 链触发 ModelVisible capture。

本测试验证 PR-12.6 的 ``_ensure_think_phase`` self-recover + PR-12.7
RunSession.close(release token)在真装配下:
- ModelVisibleLLMAdapter 包链落 5 件套到 ``model_visible/step_<NN>/``
- 派生 1 条 ``llm.request.header`` EP(spine)
- Adapter 在 cursor phase=None 时自推进 ``phase.think.fold`` EP
- RunSession.close 释放 ContextVar token
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.infrastructure.observability.spine.event_spine import EventSpine


class _MemSink:
    """无副作用 sink — 测试替身(EventSink Protocol 兼容)。"""

    def write(self, record):
        return None

    def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_mock_llm_through_brain_writes_model_visible(
    tmp_path: Path,
) -> None:
    """集成:Mock LLM 通过 ModelVisibleLLMAdapter 装饰,model_visible 真实落盘。

    验证:
    - Adapter 直接调用落 4 件套到 model_visible/step_<NN>/
    - messages.json 含 user 消息
    """
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.observability.incarnation import Incarnation
    from lca.infrastructure.observability.adapters.model_visible_llm_adapter import (
        ModelVisibleLLMAdapter,
    )
    from lca.infrastructure.observability.loop_cursor import (
        StdLoopCursor,
        install_model_visible_capture,
    )
    from lca.infrastructure.observability.loop_cursor.bind import (
        SpineWritePortAdapter,
        install_run_cursor,
    )
    from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
        StdModelVisibleCapture,
    )

    run_id = new_id("run")
    trace_id = new_id("trace")
    run_dir = tmp_path / "traces" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    events_seen: list[str] = []

    def _capture_eps(record: Any) -> None:
        ep = getattr(record, "execution_point", None)
        if ep:
            events_seen.append(ep)

    spine = EventSpine(sinks=[_MemSink()], subscribers=[_capture_eps])
    spine_port = SpineWritePortAdapter(spine)
    cursor = StdLoopCursor(
        spine=spine_port,
        run_id=run_id,
        trace_id=trace_id,
        incarnation=Incarnation(run_id=run_id, plan_ref="default", incarnation_seq=1),
    )
    cursor_token = install_run_cursor(cursor)
    capture = StdModelVisibleCapture(run_dir=run_dir)
    capture_token = install_model_visible_capture(capture)

    try:
        # Wrap Mock LLM via ModelVisibleLLMAdapter (组合根 instrument_llm 干的事)
        wrapped = ModelVisibleLLMAdapter(MockLLMAdapter(), model="mock-llm")

        # 直接调用
        result = await wrapped.complete("hello")
        assert result.text is not None

        # 3 件套落盘(ADR-0176 D4:system.json 删除,system 并入 messages.json)
        step_dirs = sorted((run_dir / "model_visible").glob("step-*"))
        assert step_dirs, f"no step dirs in {run_dir}/model_visible"
        step_dir = step_dirs[0]
        assert not (step_dir / "system.json").exists()
        for stem in ("tools", "messages", "manifest"):
            assert (step_dir / f"{stem}.json").is_file(), f"missing {stem}.json"

        # messages.json 含 user 消息(ADR-0176 D4:messages.json 是 dict 结构,含 messages_overview + messages)
        raw = json.loads((step_dir / "messages.json").read_text())
        messages = raw.get("messages", []) if isinstance(raw, dict) else raw
        assert any(
            m.get("role") == "user" and "hello" in (m.get("content") or "") for m in messages
        ), messages[:1]

        # 派生 EP:phase.think.fold + llm.request.header
        assert "phase.think.fold" in events_seen
        assert "llm.request.header" in events_seen

    finally:
        from lca.infrastructure.observability.loop_cursor import (
            reset_model_visible_capture,
            reset_run_cursor,
        )

        reset_model_visible_capture(capture_token)
        reset_run_cursor(cursor_token)


@pytest.mark.asyncio
async def test_mock_llm_writes_llm_request_header_ep_when_phase_none(
    tmp_path: Path,
) -> None:
    """PR-12.6 验证:Adapter 在 cursor phase=None 时主动 advance('think')。

    派生顺序应是:
        phase.think.fold  (Adapter 自检 advance)
        llm.request.header  (record_request_header)
    """
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.observability.incarnation import Incarnation
    from lca.infrastructure.observability.adapters.model_visible_llm_adapter import (
        ModelVisibleLLMAdapter,
    )
    from lca.infrastructure.observability.loop_cursor import (
        StdLoopCursor,
        install_model_visible_capture,
    )
    from lca.infrastructure.observability.loop_cursor.bind import (
        SpineWritePortAdapter,
        install_run_cursor,
    )
    from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
        StdModelVisibleCapture,
    )

    run_id = new_id("run")
    trace_id = new_id("trace")
    run_dir = tmp_path / "traces" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 最小 EventSpine (用内存 sink + subscribers;不依赖文件系统序列化)
    class _MemSink:
        def write(self, record):
            pass

        def close(self):
            pass

    events_seen: list[str] = []

    def _capture_eps(record: Any) -> None:
        # EventRecord 是 dataclass;无论 attr 名是 execution_point 还是 name
        ep = getattr(record, "execution_point", None) or getattr(record, "name", None)
        if ep:
            events_seen.append(ep)

    spine = EventSpine(sinks=[_MemSink()], subscribers=[_capture_eps])
    spine_port = SpineWritePortAdapter(spine)
    cursor = StdLoopCursor(
        spine=spine_port,
        run_id=run_id,
        trace_id=trace_id,
        incarnation=Incarnation(run_id=run_id, plan_ref="default", incarnation_seq=1),
    )
    cursor_token = install_run_cursor(cursor)
    capture = StdModelVisibleCapture(run_dir=run_dir)
    capture_token = install_model_visible_capture(capture)

    try:
        # 阶段 1:确认 cursor.phase == None — 这模拟生产真实状态
        assert cursor.snapshot.phase is None

        wrapped = ModelVisibleLLMAdapter(MockLLMAdapter(), model="mock-llm")
        await wrapped.complete("hi")

        assert cursor.snapshot.phase == "think"

        # 1 次 phase.think.fold(advance)+ 1 次 llm.request.header(record)
        assert "phase.think.fold" in events_seen, events_seen
        assert "llm.request.header" in events_seen, events_seen
        # 不应有重复 fold(已 THINK 不重 boost)
        assert events_seen.count("phase.think.fold") == 1, events_seen
        assert events_seen.count("llm.request.header") == 1, events_seen

    finally:
        from lca.infrastructure.observability.loop_cursor import (
            reset_model_visible_capture,
            reset_run_cursor,
        )

        reset_model_visible_capture(capture_token)
        reset_run_cursor(cursor_token)
