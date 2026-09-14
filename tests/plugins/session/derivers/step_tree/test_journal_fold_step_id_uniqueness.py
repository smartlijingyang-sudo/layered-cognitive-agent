"""fold_step_tree step_id 唯一性 + 单源 llm.request.header 切步(回归:run_3cf06424f0b7)。

step 边界由 ``llm.request.header`` 唯一驱动(SSOT);frame.phase 由
``phase.<name>.fold`` 唯一决定,不读 payload.phase。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def test_single_llm_request_header_creates_one_step() -> None:
    """单条 llm.request.header(step-001)→ 1 个 step,phase 默认 'think'(LLM 边界专属)。

    frame.phase 不由 payload 决定;fold 仅在 phase.<name>.fold 事件到达
    时写入 phase 字段(默认 think)。
    """
    events = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001"},
            "when": 1_000,
        },
        {"execution_point": "phase.think.fold", "payload": {"summary": "respond"}, "when": 1_001},
    ]
    doc = fold_step_tree(events, run_id="r_single")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"
    assert doc.steps[0].phase == "think"


def test_multi_round_think_no_duplicate_step_id() -> None:
    """多轮 llm.request.header → N 步,step_id 严格唯一。

    回归 run_3cf06424f0b7:journal.json 出现 step-001 / step-001 / step-002
    三步,doctor H3 broken 'duplicate step_id'。根因是 fold 状态机读两个
    生产者的 step_id(cursor writable.step.start + hook llm.request.header)
    在不同分支走出重复 frame。
    修复:fold 只看 llm.request.header 一个 EP 切步,关旧开新按出现顺序,
    step_id 直接从 payload 取(无升级、无合并、无隐式开窗)。
    """
    events = []
    for i in range(3):
        ts = 1_000 + i * 1_000
        sid = f"step-{i + 1:03d}"
        events.extend(
            [
                {"execution_point": "llm.request.header", "payload": {"step_id": sid}, "when": ts},
                {
                    "execution_point": "phase.think.fold",
                    "payload": {"summary": "respond"},
                    "when": ts + 1,
                },
            ]
        )
    doc = fold_step_tree(events, run_id="r_multi_round")
    assert len(doc.steps) == 3
    step_ids = [s.step_id for s in doc.steps]
    assert len(step_ids) == len(set(step_ids)), f"duplicate step_id: {step_ids}"
    assert step_ids == ["step-001", "step-002", "step-003"]
    assert [s.step_index for s in doc.steps] == [1, 2, 3]


def test_session_shaped_events_unaffected_by_field_changes() -> None:
    """Session 形态事件(spine.* CATEGORY 前缀)走 _coerce 反查路径。

    fold 切步只看 llm.request.header,Session 形态反查后与 spine 形态
    等价;无第二生产者在 Session 流上注入额外 step 边界。
    """
    events = [
        {
            "type": "spine.llm.request.header",
            "data": {"step_id": "step-001", "model": "qwen3.7-plus"},
            "time": 1_000,
        },
        {"type": "spine.phase.think.fold", "data": {"summary": "respond"}, "time": 1_001},
    ]
    doc = fold_step_tree(events, run_id="r_session")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"
    assert doc.steps[0].phase == "think"
