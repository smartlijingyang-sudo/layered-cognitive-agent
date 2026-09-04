"""Doctor fold/sidecar dual-rail 测试(ADR-0185 PR-3.1)。

覆盖 ``_scan_xref`` 的 tool_schema_count 双轨逻辑:

1. spine 有 ``spine.llm.request.header`` 且 tools 非空 →
   ``tool_schema_count > 0``,``tool_schema_source == "fold"``;
   H-mv-journal ok=True。
2. spine 无 model-visible 事件但 sidecar ``tools.json`` 存在 →
   fallback 仍能计数,``tool_schema_source == "sidecar"``。
3. 两边都没有 → ``tool_schema_count == -1``,H-mv-journal ok=None。
4. tools 全是 ``{}`` → ``tool_schema_count == 0`` /
   ``tool_schema_empty_count > 0``,H-mv-journal ok=False。

不碰 PR-4(不删 capture 实现)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lca.contracts.models.observability import (
    JournalMetadata,
    empty_document,
)
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.plugins.transport.webserver.handlers.runs.doctor.step_check import (
    diagnose_step_tree,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _write_minimal_journal(run_dir: Path, *, run_id: str = "r1") -> Path:
    """写一份最小 journal.json(0 step,completed);H-mv-journal 不依赖 step 内容。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="test")
    doc = empty_document(run_id=run_id, trace_id="t1", metadata=meta, started_at=0.0)
    from lca.contracts.models.observability import close_document

    doc = close_document(doc, outcome="completed", closed_at=1.0)
    path = run_dir / "journal.json"
    JournalDocumentWriter(path).write(doc)
    return path


def _write_spine_jsonl(run_dir: Path, run_id: str, events: list[dict[str, Any]]) -> Path:
    """写 spine ledger 到 ``<run_dir>/<run_id>.spine.jsonl``。"""
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    spine_path.parent.mkdir(parents=True, exist_ok=True)
    with spine_path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False))
            fh.write("\n")
    return spine_path


def _make_spine_event(
    *,
    category: str,
    payload: dict[str, Any],
    execution_point: str = "llm.call.start",
) -> dict[str, Any]:
    """构造 SpineEventRecord 9 键字节布局(与 fold 测试对齐)。"""
    return {
        "event_id": f"evt-{abs(hash(json.dumps(payload, sort_keys=True))) % 10000:04d}",
        "category": category,
        "execution_point": execution_point,
        "channel": "fact",
        "payload": payload,
        "ts": "2026-09-04T00:00:00+00:00",
        "causation_id": None,
        "prev_event_hash": None,
        "event_hash": None,
        "trace_id": None,
    }


def _write_sidecar_tools(run_dir: Path, step_id: str, tools: list[dict[str, Any]]) -> None:
    """写 ``<run_dir>/model_visible/<step_id>/tools.json``(sidecar 路径)。"""
    mv_step_dir = run_dir / "model_visible" / step_id
    mv_step_dir.mkdir(parents=True, exist_ok=True)
    (mv_step_dir / "tools.json").write_text(json.dumps(tools, ensure_ascii=False), encoding="utf-8")


# ── 场景 1: spine fold 路径 — tools 非空 → tool_schema_count > 0, source=fold ──


def test_fold_path_tools_nonempty_yields_positive_count_and_fold_source(
    tmp_path: Path,
) -> None:
    """spine 有 ``spine.llm.request.header`` 且 tools 非空 → count > 0 + source=fold。"""
    run_id = "r1"
    tools_payload = [
        {"name": "read_file", "parameters": {"type": "object"}},
        {"name": "run_command", "parameters": {"type": "object"}},
    ]
    spine_events = [
        _make_spine_event(
            category="spine.llm.request.header",
            payload={
                "step_id": "step-001",
                "incarnation": 1,
                "config": {"provider": "mock", "model": "m"},
                "system": "prompt",
                "tools": tools_payload,
                "messages": [],
            },
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 2
    assert report.consistency["tool_schema_source"] == "fold"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is True
    assert "非空 schema=2" in h_mv.detail


def test_fold_path_takes_priority_over_sidecar(tmp_path: Path) -> None:
    """fold 与 sidecar 同时存在 → fold 优先;source=fold。"""
    run_id = "r1"
    # fold 路径:3 个 tools
    spine_events = [
        _make_spine_event(
            category="spine.llm.request.header",
            payload={
                "step_id": "step-001",
                "incarnation": 1,
                "config": {"provider": "mock", "model": "m"},
                "system": "p",
                "tools": [
                    {"name": "a", "parameters": {}},
                    {"name": "b", "parameters": {}},
                    {"name": "c", "parameters": {}},
                ],
                "messages": [],
            },
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    # sidecar 路径:只有 1 个 tool
    _write_sidecar_tools(
        tmp_path,
        "step-001",
        [{"name": "only_sidecar", "parameters": {}}],
    )
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 3
    assert report.consistency["tool_schema_source"] == "fold"


# ── 场景 2: spine 无 model-visible 事件 + sidecar tools.json → fallback 计数 ──


def test_sidecar_fallback_when_spine_has_no_model_visible_events(
    tmp_path: Path,
) -> None:
    """spine 存在但无 ``spine.llm.request.header`` → 回退 sidecar tools.json。"""
    run_id = "r1"
    # spine 只有认知事件,没有 model-visible
    spine_events = [
        _make_spine_event(
            category="spine.cognition.brain.perceive.start",
            payload={"state_id": "x"},
            execution_point="perceive.start",
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    # sidecar tools.json:2 个有效 tools
    _write_sidecar_tools(
        tmp_path,
        "step-001",
        [
            {"name": "tool_a", "parameters": {"type": "object"}},
            {"name": "tool_b", "parameters": {"type": "object"}},
        ],
    )
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 2
    assert report.consistency["tool_schema_source"] == "sidecar"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is True


def test_sidecar_fallback_when_no_spine_at_all(tmp_path: Path) -> None:
    """spine 完全不存在 + sidecar 存在 → 回退 sidecar,source=sidecar。"""
    run_id = "r1"
    _write_sidecar_tools(
        tmp_path,
        "step-001",
        [{"name": "tool_x", "parameters": {}}],
    )
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 1
    assert report.consistency["tool_schema_source"] == "sidecar"


# ── 场景 3: 两边都没有 → tool_schema_count == -1, hop ok=None ──


def test_both_missing_yields_negative_one_and_hop_none(tmp_path: Path) -> None:
    """spine 无 model-visible 事件且无 sidecar → count=-1,source=none, hop ok=None。"""
    run_id = "r1"
    # spine 存在但只有认知事件
    spine_events = [
        _make_spine_event(
            category="phase.think.fold",
            payload={"phase": "think", "objective": "test", "objective_kind": "user_text"},
            execution_point="phase.think.fold",
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == -1
    assert report.consistency["tool_schema_source"] == "none"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is None
    assert h_mv.ok is None and ("缺失" in h_mv.detail or "不存在" in h_mv.detail)


def test_no_spine_no_sidecar_yields_negative_one(tmp_path: Path) -> None:
    """spine 完全不存在且无 sidecar → count=-1, hop ok=None。"""
    journal = _write_minimal_journal(tmp_path, run_id="r1")

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == -1
    assert report.consistency["tool_schema_source"] == "none"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is None


# ── 场景 4: tools 全是 {} → ok=False ──


def test_fold_path_all_empty_tools_yields_ok_false(tmp_path: Path) -> None:
    """fold 路径 tools 全是 ``{}`` → count=0,empty>0, H-mv-journal ok=False。"""
    run_id = "r1"
    spine_events = [
        _make_spine_event(
            category="spine.llm.request.header",
            payload={
                "step_id": "step-001",
                "incarnation": 1,
                "config": {"provider": "mock", "model": "m"},
                "system": "p",
                "tools": [{}, {}, {}],
                "messages": [],
            },
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 0
    assert report.consistency["tool_schema_empty_count"] == 3
    assert report.consistency["tool_schema_source"] == "fold"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is False


def test_sidecar_path_all_empty_tools_yields_ok_false(tmp_path: Path) -> None:
    """sidecar fallback: tools.json 全是 ``{}`` → H-mv-journal ok=False。"""
    run_id = "r1"
    # 无 fold 事件 → 走 sidecar
    spine_events = [
        _make_spine_event(
            category="phase.think.fold",
            payload={"phase": "think"},
            execution_point="phase.think.fold",
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    _write_sidecar_tools(tmp_path, "step-001", [{}, {}])
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 0
    assert report.consistency["tool_schema_empty_count"] == 2
    assert report.consistency["tool_schema_source"] == "sidecar"
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is False


# ── 边界:fold 路径空 tools list(不是 [{},{}] 而是 []) ──


def test_fold_path_empty_tools_list_falls_to_sidecar(tmp_path: Path) -> None:
    """fold 事件 tools=[](空 list)→ fold 未命中(仍 -1),回退 sidecar。

    ``tools`` 为空 list 时 ``isinstance(tools_list, list) and tools_list``
    为 False,不算 fold 命中;继续检查 sidecar。
    """
    run_id = "r1"
    spine_events = [
        _make_spine_event(
            category="spine.llm.request.header",
            payload={
                "step_id": "step-001",
                "incarnation": 1,
                "config": {"provider": "mock", "model": "m"},
                "system": "p",
                "tools": [],
                "messages": [],
            },
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    _write_sidecar_tools(
        tmp_path,
        "step-001",
        [{"name": "sidecar_tool", "parameters": {}}],
    )
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    # fold 空 list → fold 未命中 → 走 sidecar
    assert report.consistency["tool_schema_count"] == 1
    assert report.consistency["tool_schema_source"] == "sidecar"


# ── 边界:mixed empty/non-empty tools ──


def test_fold_path_mixed_empty_and_nonempty_tools(tmp_path: Path) -> None:
    """fold tools 含空与非空 dict → count = 非空数,empty_count = 空数。"""
    run_id = "r1"
    spine_events = [
        _make_spine_event(
            category="spine.llm.request.header",
            payload={
                "step_id": "step-001",
                "incarnation": 1,
                "config": {},
                "system": "p",
                "tools": [
                    {"name": "valid", "parameters": {}},
                    {},
                    {"name": "also_valid", "parameters": {}},
                    {},
                ],
                "messages": [],
            },
        ),
    ]
    _write_spine_jsonl(tmp_path, run_id, spine_events)
    journal = _write_minimal_journal(tmp_path, run_id=run_id)

    report = diagnose_step_tree(journal, mode="backend")

    assert report.consistency["tool_schema_count"] == 2
    assert report.consistency["tool_schema_empty_count"] == 2
    assert report.consistency["tool_schema_source"] == "fold"
    # H-mv-journal: count > 0 but empty_count > 0 → ok=False(empty 存在)
    h_mv = report.hops["H-mv-journal"]
    assert h_mv.ok is False
    assert "空 dict schema" in h_mv.detail
