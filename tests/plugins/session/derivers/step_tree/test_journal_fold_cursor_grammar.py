"""fold_step_tree 单源 step 边界(llm.request.header)回归测试。

SSOT:``llm.request.header`` 是 step 边界唯一驱动 EP;fold 不再读
``writable.step.start`` / ``writable.step.end`` / ``brain.think.start/end``,
不再做"原地升级""空帧合并""隐式开窗"等特殊路径。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def _hdr(sid: str, when: int, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"step_id": sid}
    payload.update(extra)
    return {"execution_point": "llm.request.header", "payload": payload, "when": when}


def _phase(kind: str, when: int, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    payload.update(extra)
    return {"execution_point": f"phase.{kind}.fold", "payload": payload, "when": when}


def test_session_shaped_prefixed_events_fold_step_and_outcome() -> None:
    """Session 形态事件(spine.* CATEGORY 前缀)走 _coerce 反查,等价 spine 形态。"""
    events = [
        {"type": "spine.llm.request.header", "data": {"step_id": "step-001"}, "time": 1_000},
        {"type": "spine.phase.think.fold", "data": {"summary": "respond"}, "time": 1_001},
    ]
    doc = fold_step_tree(events, run_id="r_session")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"


def test_header_without_step_id_is_skipped() -> None:
    """llm.request.header 缺 step_id → fold 不开新 frame(ssot 边界)。"""
    events = [
        _hdr("step-001", when=1),
        {"execution_point": "llm.request.header", "payload": {}, "when": 2},  # no step_id
        _phase("think", when=3),
    ]
    doc = fold_step_tree(events, run_id="r_no_stepid")
    # 第二条 header 缺 step_id 不开新 step;最终 1 步
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"


def test_header_step_id_must_match_payload_step_id() -> None:
    """payload.step_id 即 step_id 真值,fork 自 hook 端派生。"""
    events = [
        _hdr("step-001", when=1),
        _phase("think", when=2),
        _hdr("step-002", when=3),
        _phase("think", when=4),
    ]
    doc = fold_step_tree(events, run_id="r_seq")
    assert [s.step_id for s in doc.steps] == ["step-001", "step-002"]


def test_step_thinking_record_defensive_without_text_preview() -> None:
    """step.thinking.record 缺字段 → fold 不抛,产出空 thinking。"""
    events = [
        _hdr("step-001", when=1),
        {"execution_point": "step.thinking.record", "payload": {}, "when": 2},
    ]
    doc = fold_step_tree(events, run_id="r_thinking")
    assert len(doc.steps) == 1
    assert doc.steps[0].thinking is not None


def test_two_explicit_boundaries_make_two_steps() -> None:
    """两条 llm.request.header(不同 step_id)→ 2 步。"""
    events = [
        _hdr("step-001", when=1),
        _phase("think", when=2),
        _hdr("step-002", when=3),
        _phase("think", when=4),
    ]
    doc = fold_step_tree(events, run_id="r_two")
    assert len(doc.steps) == 2
    assert [s.step_id for s in doc.steps] == ["step-001", "step-002"]


def test_phase_fold_without_header_has_zero_steps() -> None:
    """纯 phase.fold 流(无 llm.request.header)→ 0 步,phases 计数 ≥ 1。"""
    events = [
        _phase("think", when=1, summary="a"),
        _phase("stop", when=2, summary="b"),
    ]
    doc = fold_step_tree(events, run_id="r_phases_only")
    assert len(doc.steps) == 0
    assert doc.totals is not None
    assert doc.totals.phases >= 2
