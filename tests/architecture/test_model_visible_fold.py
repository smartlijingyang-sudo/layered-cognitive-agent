"""ModelVisible fold byte-level coverage（ADR-0185 §3.5 + §3.7 + I-MV-2）。

PR-3(ADR-0185)负责:验证 :func:`lca_kernel.events.fold.foldRequestHeader`
对 ``<run_id>.spine.jsonl`` 落盘事件的 5 场景字节级重建能力。
本测试是架构测试 — 与 PR-0 ``tests/lca_kernel/events/test_fold.py``
的 5 场景测试并列,后者走 dict fixture,本测试走真实 ``SpineEventRecord``
落盘 + :class:`SpineReader` + :class:`FoldedModelVisible` 端到端,
覆盖 PR-3 viewer 路径的真实数据流。

5 场景(对齐 ADR-0185 §3.5 fold 矩阵):

1. **initial emit** —— 首次 ``spine.llm.request.header`` 落盘,fold
   重建到唯一有效 header(``reason=initial``)。
2. **same-header no-emit** —— 连续两条 canonical 相同 header 落盘
   (publisher 未 fold 命中场景,旁路写入两条),fold 取最近一条仍
   与 ``canonicalHeader`` 字节级等。
3. **system change** —— system 字段变更,fold 重建到新 system。
4. **tools change** —— tools 列表变更,fold 重建到新 tools(顺序敏感)。
5. **new series** —— 同 header 但开新 series(retry 路径),fold 取
   最近一条 series 的 header;新 fold series 不污染旧 series。

不动:本测试不写旁路文件 / 不调 LLM;纯 IO + 纯函数 fold。
delete-when:N/A(I-MV-2 守护测试,留作长期回归)。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.replay.fold_source import (
    SOURCE_FOLD,
    fold_model_visible,
)
from lca_kernel.events.fold import (
    EpochHeader,
    canonicalHeader,
    foldRequestHeader,
    headerEquals,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _make_request_header_payload(
    *,
    step_id: str,
    incarnation: int,
    config: Mapping[str, Any],
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
        "config": dict(config),
        "system": system,
        "tools": list(tools),
        "messages": list(messages),
        "manifest": None,
        "reason": reason,
        "previous_header_digest": previous_header_digest,
    }


def _make_assistant_payload(
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
        "usage": dict(usage or {"prompt_tokens": 0, "completion_tokens": 0}),
        "header_digest": header_digest,
    }


def _build_spine_event_dict(
    *,
    category: str,
    payload: Mapping[str, Any],
    event_id: str,
    execution_point: str = "llm.call.start",
    channel: str = "fact",
) -> dict[str, Any]:
    """构造 :class:`SpineEventRecord` 9 键字节布局（与 ``to_dict`` 对齐）。

    字段名 / 字段顺序与 :meth:`SpineEventRecord.to_dict` 严格一致;
    测试不构建 chain（causation_id / prev_event_hash / event_hash 全 None）。
    """
    return {
        "event_id": event_id,
        "category": category,
        "execution_point": execution_point,
        "channel": channel,
        "payload": dict(payload),
        "ts": "2026-09-04T00:00:00+00:00",
        "causation_id": None,
        "prev_event_hash": None,
        "event_hash": None,
        "trace_id": None,
    }


def _write_spine_jsonl(spine_path: Path, events: list[dict[str, Any]]) -> None:
    """每行 1 个 event 写入 ``<run_id>.spine.jsonl``。"""
    spine_path.parent.mkdir(parents=True, exist_ok=True)
    with spine_path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False))
            fh.write("\n")


def _run_dir_with_spine(
    tmp_path: Path,
    run_id: str,
    events: list[dict[str, Any]],
) -> Path:
    """写 spine ledger 到 ``tmp_path/runs/<run_id>/<run_id>.spine.jsonl``。

    返回 run_dir 路径(便于 ``fold_model_visible(run_dir=...)``)。
    """
    run_dir = tmp_path / "runs" / run_id
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    _write_spine_jsonl(spine_path, events)
    return run_dir


# ── 场景 1: 首次 emit(reason=initial) ────────────────────────────────


def test_fold_initial_emit_from_spine_jsonl(tmp_path: Path) -> None:
    """场景 1: 唯一一条 ``spine.llm.request.header`` 落盘 → fold 重建 initial header。

    端到端数据流:写 spine.jsonl → SpineReader.events() → foldRequestHeader
    → 字节级等 canonicalHeader(EpochHeader(...))。
    """
    run_id = "run_fold_initial"
    payload = _make_request_header_payload(
        step_id="step-001",
        incarnation=1,
        config={"provider": "mock", "model": "m"},
        system="first prompt",
    )
    events = [
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=payload,
            event_id="evt-001",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")

    assert folded is not None, "fold 应从 spine 重建"
    assert folded.header is not None
    assert folded.source == SOURCE_FOLD
    assert folded.digest_verified is True
    # canonical:空 tools 归一为 ()。
    assert folded.header.tools == ()
    assert folded.header.system == "first prompt"
    # fold header 与预期 canonical header 字段级等。
    expected = canonicalHeader(
        EpochHeader(
            config={"provider": "mock", "model": "m"},
            system="first prompt",
        )
    )
    assert folded.header == expected


# ── 场景 2: 同 header 不发(fold 跳过)→ fold 取最近等值 header ───────────


def test_fold_same_header_no_emit_still_reconstructs(tmp_path: Path) -> None:
    """场景 2: 两条 canonical 相同 header 落盘(publisher fold 命中失败场景)。

    fold 模块不依赖 publisher「不发」决策;只对落盘事件流负责;验证:
    两条 canonical 相同 header 在流里时,fold 结果与任一条 canonical
    header 字节级等(I-MV-2 守护:fold 重建不依赖 reason 字段)。
    """
    run_id = "run_fold_same"
    common = _make_request_header_payload(
        step_id="step-001",
        incarnation=1,
        config={"provider": "mock", "model": "m"},
        system="same prompt",
        tools=({"name": "tool-a", "parameters": {"type": "object"}},),
    )
    events = [
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=common,
            event_id="evt-001",
        ),
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=common,
            event_id="evt-002",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is not None
    expected = canonicalHeader(
        EpochHeader(
            config={"provider": "mock", "model": "m"},
            system="same prompt",
            tools=({"name": "tool-a", "parameters": {"type": "object"}},),
        )
    )
    assert folded.header == expected
    # headerEquals 字节级等 — fold 重建与 publisher 落盘内容一致。
    assert headerEquals(folded.header, expected) is True


# ── 场景 3: system 变更 → fold 重建到变更后 system ─────────────────────


def test_fold_system_change_reconstructs_to_new_system(tmp_path: Path) -> None:
    """场景 3: system 字段变更 → fold 重建到最新 system(reason=change)。"""
    run_id = "run_fold_system_change"
    events = [
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-001",
                incarnation=1,
                config={"provider": "mock", "model": "m"},
                system="prompt v1",
            ),
            event_id="evt-001",
        ),
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-002",
                incarnation=1,
                config={"provider": "mock", "model": "m"},
                system="prompt v2",
            ),
            event_id="evt-002",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    # step-001 fold 到 v1
    folded_001 = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded_001 is not None
    assert folded_001.header is not None
    assert folded_001.header.system == "prompt v1"

    # step-002 fold 到 v2
    folded_002 = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-002")
    assert folded_002 is not None
    assert folded_002.header is not None
    assert folded_002.header.system == "prompt v2"

    # fold 端到端(SpineReader.events() 直接)与 fold_model_visible 字节级等。
    from lca_kernel.events.reader import SpineReader

    records = list(SpineReader(run_id=run_id, path=run_dir / f"{run_id}.spine.jsonl").events())
    direct_fold = foldRequestHeader(records, step_id="step-002")
    assert direct_fold is not None
    assert direct_fold == folded_002.header


# ── 场景 4: tools 变更(顺序敏感) → fold 重建到新 tools ────────────────


def test_fold_tools_change_reconstructs_to_new_tools(tmp_path: Path) -> None:
    """场景 4: tools 列表变更(顺序敏感)→ fold 重建到新 tools。"""
    run_id = "run_fold_tools_change"
    events = [
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-001",
                incarnation=1,
                config={"provider": "mock", "model": "m"},
                system="sys",
                tools=(
                    {"name": "tool-a", "parameters": {"type": "object"}},
                    {"name": "tool-b", "parameters": {"type": "object"}},
                ),
            ),
            event_id="evt-001",
        ),
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-002",
                incarnation=1,
                config={"provider": "mock", "model": "m"},
                system="sys",
                tools=(
                    {"name": "tool-b", "parameters": {"type": "object"}},
                    {"name": "tool-c", "parameters": {"type": "object"}},
                ),
            ),
            event_id="evt-002",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    folded_002 = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-002")
    assert folded_002 is not None
    assert folded_002.header is not None
    # tools 顺序敏感:folded 应是 [b, c](非 [a, b, c])
    folded_tool_names = [t["name"] for t in folded_002.header.tools]
    assert folded_tool_names == ["tool-b", "tool-c"]


# ── 场景 5: 新 series(retry 同 header)→ fold 取最近一条 series ────────


def test_fold_new_series_opens_with_same_header(tmp_path: Path) -> None:
    """场景 5: 同 header 但开新 series(retry 路径)→ fold 取最近 series 的 header。

    验证 ``foldRequestHeader`` 不被「同 header」卡住;publisher 在 retry
    路径下会强制发 ``series`` reason 写盘;fold 端取最近一条 series 的
    header(与最近一个 ``spine.llm.request.header`` 事件对应),新 series
    不污染旧 series(I-MV-2 守护)。

    本场景下,step_id 相同但 incarnation 递增表示 retry / 新 series;
    fold 按 step_id 过滤后取最近事件为「最近 series」语义。
    """
    run_id = "run_fold_new_series"
    common = {"provider": "mock", "model": "m"}
    events = [
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-001",
                incarnation=1,
                config=common,
                system="prompt",
                reason="initial",
            ),
            event_id="evt-001",
        ),
        # 同 step / 同 header / incarnation=2 → 新 series(retry 路径)
        _build_spine_event_dict(
            category="spine.llm.request.header",
            payload=_make_request_header_payload(
                step_id="step-001",
                incarnation=2,
                config=common,
                system="prompt",
                reason="series",
                previous_header_digest="sha256:abc",
            ),
            event_id="evt-002",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is not None
    # fold header 与任一条 canonical header 字节级等(系列内同 header);
    # 但 ``messages`` 来自最近一条 payload(对应「最近 series」语义)。
    assert folded.messages == () or len(folded.messages) == 0
    expected = canonicalHeader(
        EpochHeader(config=common, system="prompt"),
    )
    assert folded.header is not None
    assert headerEquals(folded.header, expected) is True


# ── 边界:spine 缺失 / 无 model-visible 事件流 → fold_model_visible None ──


def test_fold_returns_none_when_spine_missing(tmp_path: Path) -> None:
    """spine ledger 不存在 → ``fold_model_visible`` 返回 ``None``(不抛)。"""
    folded = fold_model_visible(
        run_dir=tmp_path / "runs" / "run_no_spine",
        run_id="run_no_spine",
        step_id="step-001",
    )
    assert folded is None


def test_fold_returns_none_when_no_model_visible_events(tmp_path: Path) -> None:
    """spine 存在但无 ``spine.llm.request.header`` 事件流 → ``None``。"""
    run_id = "run_no_model_visible"
    events = [
        _build_spine_event_dict(
            category="spine.cognition.brain.perceive.start",
            payload={"state_id": "x"},
            event_id="evt-001",
        ),
    ]
    run_dir = _run_dir_with_spine(tmp_path, run_id, events)

    folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id="step-001")
    assert folded is None
