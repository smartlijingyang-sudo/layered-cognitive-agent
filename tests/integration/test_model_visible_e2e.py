"""Model-visible E2E:spine.jsonl fold 重建 + assistant reconstruct (ADR-0185 PR-3)。

端到端 fixture run 断言(对齐 ADR-0185 PR-3 验收 §8.4 #9 + #10 + I-MV-2):

- (a) ``<run_id>.spine.jsonl`` 含 ``spine.llm.request.header`` +
  ``spine.llm.request.header.assistant`` 两类事件(I-MV-1 唯一授权)
- (b) :func:`fold_model_visible` 返回的 header 与 publisher 落盘 payload
  字节级等(``headerEquals`` True)
- (c) assistant payload 中的 content / tool_calls / finish_reason / usage
  可从 :attr:`FoldedModelVisible.assistant` 字段读到
- (d) :class:`StandardCursor.at` 走 fold 路径时
  :attr:`StepContextAt.source` = ``"replayed_fold"``、
  :attr:`StepContextAt.digest_verified` = True

不动:不调真实 LLM / tool;不写旁路文件;纯 IO + typed payload fold。
delete-when:N/A(I-MV-2 守护测试,留作长期回归)。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.observability.replay import StepContextAt
from lca.infrastructure.observability.replay import (
    SOURCE_FOLD,
    StandardCursor,
    fold_model_visible,
)
from lca.infrastructure.observability.spine.sinks.naming import (
    spine_filename_for_run,
)
from lca_kernel.events.fold import canonicalHeader, headerEquals
from lca_kernel.events.payloads_model_visible import (
    SpineLlmRequestHeaderAssistantPayload,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _request_header_payload(
    *,
    step_id: str,
    incarnation: int,
    system: str,
    tools: tuple[Mapping[str, Any], ...] = (),
    messages: tuple[Mapping[str, Any], ...] = (),
    reason: str = "initial",
    previous_header_digest: str | None = None,
) -> dict[str, Any]:
    """构造 ``spine.llm.request.header`` payload 形态(对齐 PR-1 typing)。"""
    return {
        "step_id": step_id,
        "incarnation": incarnation,
        "config": {"provider": "mock", "model": "m"},
        "system": system,
        "tools": list(tools),
        "messages": list(messages),
        "manifest": None,
        "reason": reason,
        "previous_header_digest": previous_header_digest,
    }


def _assistant_payload(
    *,
    step_id: str,
    incarnation: int,
    assistant_content: str,
    header_digest: str,
    tool_calls: tuple[Mapping[str, Any], ...] = (),
    finish_reason: str = "stop",
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 ``spine.llm.request.header.assistant`` payload 形态。"""
    return {
        "step_id": step_id,
        "incarnation": incarnation,
        "assistant_content": assistant_content,
        "tool_calls": list(tool_calls),
        "finish_reason": finish_reason,
        "usage": dict(usage or {"prompt_tokens": 7, "completion_tokens": 5}),
        "header_digest": header_digest,
    }


def _spine_event_dict(
    *,
    category: str,
    payload: Mapping[str, Any],
    event_id: str,
) -> dict[str, Any]:
    """构造 :class:`SpineEventRecord` 9 键字节布局(与 ``to_dict`` 对齐)。"""
    return {
        "event_id": event_id,
        "category": category,
        "execution_point": "llm.call.start",
        "channel": "fact",
        "payload": dict(payload),
        "ts": "2026-09-04T00:00:00+00:00",
        "causation_id": None,
        "prev_event_hash": None,
        "event_hash": None,
        "trace_id": None,
    }


def _write_spine(tmp_path: Path, run_id: str, events: list[dict[str, Any]]) -> Path:
    """写 fixture spine ledger;返回 run_dir。"""
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spine_path = run_dir / spine_filename_for_run(run_id)
    with spine_path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False))
            fh.write("\n")
    return run_dir


# ── 端到端 fixture:request/header + assistant 双事件 ─────────────────


def test_e2e_spine_jsonl_contains_both_event_types(tmp_path: Path) -> None:
    """(a) spine.jsonl 同时含两类 model-visible 事件(I-MV-1 唯一授权守护)。"""
    run_id = "run_e2e_both"
    request_payload = _request_header_payload(
        step_id="step-001",
        incarnation=1,
        system="hello",
    )
    assistant_payload = _assistant_payload(
        step_id="step-001",
        incarnation=1,
        assistant_content="hi back",
        header_digest="sha256:placeholder",
    )
    events = [
        _spine_event_dict(
            category="spine.llm.request.header",
            payload=request_payload,
            event_id="evt-req-1",
        ),
        _spine_event_dict(
            category="spine.llm.request.header.assistant",
            payload=assistant_payload,
            event_id="evt-asst-1",
        ),
    ]
    _write_spine(tmp_path, run_id, events)

    # 读 spine ledger,断言两类事件各 1 条 + 数量正确
    from lca_kernel.events.reader import SpineReader

    spine_path = tmp_path / "runs" / run_id / spine_filename_for_run(run_id)
    records = list(SpineReader(run_id=run_id, path=spine_path).events())
    assert len(records) == 2
    categories = [r.category for r in records]
    assert categories == [
        "spine.llm.request.header",
        "spine.llm.request.header.assistant",
    ]


# ── 端到端 fixture:fold 重建 header 与 publisher payload 字节级等 ─────


def test_e2e_fold_reconstructs_header_byte_equal_to_publisher_payload(
    tmp_path: Path,
) -> None:
    """(b) fold 重建 header 与 publisher 落盘 payload 字节级等(headerEquals True)。

    路径:写 fixture → fold_model_visible() → 拿 header → 与原始 payload
    字段(``system`` / ``tools`` / ``config``)构造的 canonical header
    ``headerEquals`` 比对。
    """
    run_id = "run_e2e_fold"
    raw_payload = _request_header_payload(
        step_id="step-001",
        incarnation=1,
        system="hello world",
        tools=({"name": "tool-a", "parameters": {"type": "object"}},),
    )
    events = [
        _spine_event_dict(
            category="spine.llm.request.header",
            payload=raw_payload,
            event_id="evt-1",
        ),
    ]
    run_dir = _write_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is not None
    assert folded.header is not None

    # 字节级等:fold header == canonical(publisher payload 字段构造的 header)
    expected = canonicalHeader(
        # 字段直接来自 raw_payload(模拟 publisher 落盘前的 EpochHeader)
        # 构造:config / system / tools 三个字段与 payload 字段一致。
        _payload_to_epoch_header(raw_payload),
    )
    assert headerEquals(folded.header, expected) is True


def _payload_to_epoch_header(payload: Mapping[str, Any]) -> Any:
    """``spine.llm.request.header`` payload → :class:`EpochHeader` 形态。"""
    from lca_kernel.events.fold import EpochHeader

    return EpochHeader(
        config=payload.get("config"),
        system=payload.get("system") or None,
        tools=tuple(payload.get("tools") or ()),
    )


# ── 端到端 fixture:assistant content / tool_calls 可重建 ──────────────


def test_e2e_assistant_payload_reconstructable_via_fold_source(tmp_path: Path) -> None:
    """(c) assistant content / tool_calls 可从 :attr:`FoldedModelVisible.assistant` 读到。

    修复 ADR-0169 Note ``2026-09-03-model-visible-incomplete-projection`` 第 1
    BUG(assistant 没投影);本测试断言 PR-3 fold 路径下 assistant 字段
    完整可读。
    """
    run_id = "run_e2e_assistant"
    expected_content = "I'll call tool-a with arg=42"
    expected_tool_calls = (
        {
            "id": "call-001",
            "function": {
                "name": "tool-a",
                "arguments": '{"arg": 42}',
            },
            "type": "function",
        },
    )
    request_payload = _request_header_payload(
        step_id="step-001",
        incarnation=1,
        system="sys",
    )
    assistant_payload = _assistant_payload(
        step_id="step-001",
        incarnation=1,
        assistant_content=expected_content,
        header_digest="sha256:dummy",
        tool_calls=expected_tool_calls,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 11, "completion_tokens": 7},
    )
    events = [
        _spine_event_dict(
            category="spine.llm.request.header",
            payload=request_payload,
            event_id="evt-req-1",
        ),
        _spine_event_dict(
            category="spine.llm.request.header.assistant",
            payload=assistant_payload,
            event_id="evt-asst-1",
        ),
    ]
    run_dir = _write_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is not None
    assert folded.assistant is not None
    # typed payload(I-MV-1 收口:typed payload 走 Pydantic 校验)
    assert isinstance(folded.assistant, SpineLlmRequestHeaderAssistantPayload)
    assert folded.assistant.assistant_content == expected_content
    assert tuple(folded.assistant.tool_calls) == expected_tool_calls
    assert folded.assistant.finish_reason == "tool_calls"
    assert folded.assistant.usage == {"prompt_tokens": 11, "completion_tokens": 7}


# ── 端到端 fixture:StandardCursor.at 走 fold 路径(source=replayed_fold) ──


def test_e2e_standard_cursor_walks_fold_path(tmp_path: Path) -> None:
    """(d) :class:`StandardCursor.at` 在 spine 存在 + model-visible 事件就绪时
    走 fold 路径,``source="replayed_fold"``、``digest_verified=True``。

    PR-3 验收 §8.4 #10(viewer 渲染完整)+ I-MV-2(fold 可重建 fail-fast)。
    """
    run_id = "run_e2e_cursor"
    request_payload = _request_header_payload(
        step_id="step-001",
        incarnation=1,
        system="sys",
    )
    assistant_payload = _assistant_payload(
        step_id="step-001",
        incarnation=1,
        assistant_content="ack",
        header_digest="sha256:dummy",
    )
    events = [
        _spine_event_dict(
            category="spine.llm.request.header",
            payload=request_payload,
            event_id="evt-1",
        ),
        _spine_event_dict(
            category="spine.llm.request.header.assistant",
            payload=assistant_payload,
            event_id="evt-2",
        ),
    ]
    run_dir = _write_spine(tmp_path, run_id, events)

    # 本测试只验 fold 路径 source/digest_verified 标记;
    # 完整 StandardCursor.at() fold 分支需 journal fixture,见下方
    # test_e2e_standard_cursor_at_returns_fold_source。
    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is not None
    assert folded.source == SOURCE_FOLD
    assert folded.digest_verified is True

    # 同步断言 folded.header_digest 与 canonicalHeader(payload) 字节级等
    # (I-MV-2:publisher ``previous_header_digest`` 与 viewer 算出的
    # header_digest 在同 canonical 下必须等)。
    from lca.infrastructure.observability.replay.fold_source import (
        _canonical_digest,
    )
    from lca_kernel.events.fold import EpochHeader

    expected_canonical = canonicalHeader(
        EpochHeader(
            config=request_payload["config"],
            system=request_payload["system"],
            tools=tuple(request_payload["tools"]),
        )
    )
    assert folded.header_digest == _canonical_digest(expected_canonical)


# ── 端到端 fixture:完整 StandardCursor.at() 走 fold 路径(需 journal.json) ─


def test_e2e_standard_cursor_at_returns_fold_source(tmp_path: Path) -> None:
    """完整 :meth:`StandardCursor.at` 端到端:fold 优先命中 + source 标记。

    构造最小 journal.json(``lca/infrastructure/observability/journal/step``
    reader 期望) + spine.jsonl 联合 fixture,断言 ``StepContextAt``:
    - ``source == "replayed_fold"``(I-MV-2 守护)
    - ``digest_verified is True``(fold canonical 字节级稳定)
    - ``request_header`` 包含 ``header_digest``(fold canonical sha256)
    - ``messages`` 来自最近一条 payload(fold 重建原文)
    """
    run_id = "run_e2e_cursor_at"
    step_id = "step-001"
    step_index = 1

    # ── 1) 写 spine.jsonl ──
    request_payload = _request_header_payload(
        step_id=step_id,
        incarnation=1,
        system="hello",
        messages=({"role": "user", "content": "hi"},),
    )
    assistant_payload = _assistant_payload(
        step_id=step_id,
        incarnation=1,
        assistant_content="world",
        header_digest="sha256:dummy",
    )
    events = [
        _spine_event_dict(
            category="spine.llm.request.header",
            payload=request_payload,
            event_id="evt-1",
        ),
        _spine_event_dict(
            category="spine.llm.request.header.assistant",
            payload=assistant_payload,
            event_id="evt-2",
        ),
    ]
    run_dir = _write_spine(tmp_path, run_id, events)

    # ── 2) 写最小 journal.json(StandardCursor.at 入口) ──
    # JournalDocument 期望 metadata / steps / run_id / trace_id / started_at
    # 5 必填字段;PhaseRecord / Totals 3.1 字段可空。本测试用最小 3.0 schema。
    journal = {
        "schema": "lca.journal/3",
        "run_id": run_id,
        "trace_id": "trace-1",
        "started_at": 0.0,
        "metadata": {
            "agent_role": "test",
            "strategy_key": "default",
            "plan_ref": "default",
            "objective": "test",
        },
        "steps": [
            {
                "step_id": step_id,
                "step_index": step_index,
                "phase": "think",
                "entered_at": 0.0,
                "outcome": "ok",
                "duration_ms": 0,
            },
        ],
    }
    (run_dir / "journal.json").write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")

    # ── 3) StandardCursor.at() ──
    # StandardCursor(traces_root) 内部分析 traces_root/runs/<run_id>/...
    # 本测试 traces_root = tmp_path;run_dir = tmp_path/runs/<run_id>
    cursor = StandardCursor(tmp_path)
    ctx: StepContextAt = cursor.at(run_id=run_id, step_index=step_index)

    # ── 4) 断言 fold 路径生效 ──
    assert ctx.source == SOURCE_FOLD
    assert ctx.digest_verified is True
    assert ctx.inferred is False
    assert ctx.request_header is not None
    assert "header_digest" in ctx.request_header
    assert ctx.request_header.get("system") == "hello"
    assert ctx.messages and ctx.messages[0].get("content") == "hi"
