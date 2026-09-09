"""fold_step_tree step_id 唯一性 + writable.step.start 不污染 frame.phase(回归:run_6765361accc9)。

覆盖:
- writable.step.start payload 不带 phase 字段时,frame.phase 不被 cursor
  state.phase 污染(原来从 payload.phase 读取,导致 perceive 窗口发的 LLM
  边界把 frame.phase 写成 perceive)。
- 同一 run 内多轮 think + 多 writable.step.start 不产生 duplicate step_id
  (原来因 frame.phase 错位 + phase.fold attach 路径不同导致 fold 产出
  step-001 / step-001 / step-002 三步,doctor H3 broken)。
- Session 形态事件经反查表归一后行为等价。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def test_writable_step_start_without_phase_field_keeps_frame_phase_default() -> None:
    """writable.step.start 不带 phase 字段时,frame.phase 保持 'think'(LLM 边界专属)。

    回归 run_6765361accc9:open_step 路径在 perceive phase 调用 _emit_step_start,
    payload.phase='perceive' 被 fold _begin_step 写入 frame.phase,导致
    step[1].phase='perceive' 与 phase.think.fold 决定的标准语义冲突。
    修复:writable.step.start 不再携带 phase 字段,frame.phase 由 phase.fold
    事件统一决定。
    """
    events = [
        # 第一轮 think
        {"execution_point": "brain.think.start", "payload": {}, "when": 1_000},
        # LLM 边界:record_request_header 路径(强制 think 窗口)
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "qwen3.7-plus"},
            "when": 1_001,
        },
        # writable.step.start payload 不再有 phase 字段(cursor 修复后)
        {
            "execution_point": "writable.step.start",
            "payload": {"step": 1, "run_id": "r", "step_id": "step-001"},
            "when": 1_002,
        },
        {"execution_point": "brain.think.end", "payload": {"outcome": "success"}, "when": 1_003},
        # 第二轮 think
        {"execution_point": "brain.think.start", "payload": {}, "when": 2_000},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-002", "model": "qwen3.7-plus"},
            "when": 2_001,
        },
        {
            "execution_point": "writable.step.start",
            "payload": {"step": 2, "run_id": "r", "step_id": "step-002"},
            "when": 2_002,
        },
        {"execution_point": "brain.think.end", "payload": {"outcome": "success"}, "when": 2_003},
    ]
    doc = fold_step_tree(events, run_id="r_phase_unification")
    assert len(doc.steps) == 2
    # frame.phase 在没有 phase.fold 事件时保持 'think'(LLM 边界专属默认值)
    assert [s.step_id for s in doc.steps] == ["step-001", "step-002"]
    assert [s.step_index for s in doc.steps] == [1, 2]
    assert all(s.phase == "think" for s in doc.steps)


def test_writable_step_start_with_phase_field_does_not_overwrite_frame_phase() -> None:
    """writable.step.start 即使带 phase='perceive'(旧 cursor 路径),fold 也忽略。

    防御性测试:即便上游没及时更新 cursor,payload.phase 仍存在,
    fold 必须不读它(避免回归)。
    """
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1_000},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001"},
            "when": 1_001,
        },
        # 模拟旧 cursor:payload.phase='perceive'(错误语义残留)
        {
            "execution_point": "writable.step.start",
            "payload": {
                "step": 1,
                "run_id": "r",
                "step_id": "step-001",
                "phase": "perceive",
            },
            "when": 1_002,
        },
        {"execution_point": "brain.think.end", "payload": {"outcome": "success"}, "when": 1_003},
    ]
    doc = fold_step_tree(events, run_id="r_legacy_payload_phase")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"
    # 关键断言:frame.phase 不会被 payload.phase='perceive' 污染
    assert doc.steps[0].phase == "think"


def test_multi_round_think_no_duplicate_step_id() -> None:
    """多轮 think + 多 writable.step.start:fold 产 N 步(无重复 step_id)。

    回归 run_6765361accc9:journal.json 出现 step-001 / step-001 / step-002
    三步,doctor H3 broken 'duplicate step_id'。根因是 writable.step.start
    payload.phase='perceive' 让 fold _begin_step 在升级时覆写 frame.phase,
    与 phase.think.fold 决定的 frame.phase 错位,后续 phase.fold attach
    走不同分支导致 step 数膨胀。修复后 frame.phase 由 phase.fold 决定,
    _begin_step 不再覆写 phase 字段。
    """
    events = []
    for i in range(3):
        ts = 1_000 + i * 1_000
        sid = f"step-{i + 1:03d}"
        events.extend([
            {"execution_point": "brain.think.start", "payload": {}, "when": ts},
            {
                "execution_point": "llm.request.header",
                "payload": {"step_id": sid, "model": "qwen3.7-plus"},
                "when": ts + 1,
            },
            {
                "execution_point": "writable.step.start",
                "payload": {"step": i + 1, "run_id": "r", "step_id": sid},
                "when": ts + 2,
            },
            {"execution_point": "phase.think.fold", "payload": {"summary": "respond"}, "when": ts + 3},
            {
                "execution_point": "brain.think.end",
                "payload": {"outcome": "failure"},
                "when": ts + 4,
            },
        ])
    doc = fold_step_tree(events, run_id="r_multi_round")
    assert len(doc.steps) == 3
    step_ids = [s.step_id for s in doc.steps]
    # 关键断言:无 duplicate step_id
    assert len(step_ids) == len(set(step_ids)), f"duplicate step_id: {step_ids}"
    assert step_ids == ["step-001", "step-002", "step-003"]
    # step_index 与 step_id 顺序一致
    assert [s.step_index for s in doc.steps] == [1, 2, 3]


def test_session_shaped_events_unaffected_by_phase_field_removal() -> None:
    """Session 形态事件(spine.* CATEGORY 前缀)走 _coerce 反查路径,与 payload.phase 字段无关。

    Session 形态没有 record 级 phase 字段(默认 'live'),也不读 payload.phase。
    这次修复对 Session 路径行为零影响。
    """
    events = [
        {
            "type": "spine.cognition.brain.think.start",
            "data": {"state_id": "trace_x"},
            "time": 1_000,
        },
        {
            "type": "spine.llm.request.header",
            "data": {"step_id": "step-001", "model": "qwen3.7-plus"},
            "time": 1_001,
        },
        # 注意:Session 形态 payload 里也没有 phase 字段
        {
            "type": "spine.writable.step.start",
            "data": {"step": 1, "run_id": "r", "step_id": "step-001"},
            "time": 1_002,
        },
        {
            "type": "spine.cognition.brain.think.end",
            "data": {"outcome": "success"},
            "time": 1_003,
        },
        {
            "type": "spine.phase.think.fold",
            "data": {"summary": "respond"},
            "time": 1_004,
        },
    ]
    doc = fold_step_tree(events, run_id="r_session_unaffected")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"
    assert doc.steps[0].phase == "think"
