"""fold run 终态权威回归:`kernel.run.stop` 是 run-outcome 唯一权威。

现场证据 run_eed09c1df112(650 events)尾序:

    lifecycle.finally              payload {"boundary":"terminal_driver","outcome":"success"}
    runtime.event_publisher.publish payload {"event_type":"failed","outcome":"success"}
    agent_loop.iteration.end        payload {"outcome":"success"}
    kernel.run.stop                 payload {"outcome":"failure","run_id":"run_eed09c1df112"}

两个被锁住的缺陷:

1. ``kernel.run.stop`` 的 outcome 在 spine 记录里只存在于 ``payload``;fold 曾读
   顶层 ``outcome``,且词表不含 kernel 实际发的 ``"failure"`` —— 权威事件被整条忽略。
2. ``lifecycle.finally`` 报的是 teardown 边界成功(``emit_lifecycle_finally``
   硬编码 ``outcome="success"``),不是 run 终态;它先于 ``kernel.run.stop`` 到达,
   曾把失败 run 折成 ``completed``。

fixture 用 :class:`SpineReader.read_dicts` 的真实记录形态(payload 内嵌 outcome)。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

RUN_ID = "run_eed09c1df112"


def _spine(
    ep: str,
    payload: dict[str, object],
    *,
    event_id: str,
    ts: str,
) -> dict[str, object]:
    """构造 spine ledger 真实记录形态(``<run_id>.spine.jsonl`` 逐行 dict)。"""
    return {
        "category": f"spine.{ep}",
        "causation_id": None,
        "channel": "fact",
        "event_hash": None,
        "event_id": event_id,
        "execution_point": ep,
        "payload": payload,
        "prev_event_hash": None,
        "trace_id": None,
        "ts": ts,
    }


def _run_stop(outcome: object, *, event_id: str = "run:1040") -> dict[str, object]:
    return _spine(
        "kernel.run.stop",
        {"outcome": outcome, "run_id": RUN_ID, "trace_id": "trace_1a60d32e11f8"},
        event_id=event_id,
        ts="2026-09-16T16:29:01.158948+00:00",
    )


def _publisher(event_type: str, *, event_id: str = "run:1035") -> dict[str, object]:
    return _spine(
        "runtime.event_publisher.publish",
        {"event_type": event_type, "outcome": "success", "trace_id": "trace_1a60d32e11f8"},
        event_id=event_id,
        ts="2026-09-16T16:29:01.155200+00:00",
    )


# run_eed09c1df112 尾部 4 条,payload 逐字复制自现场 spine。
_REAL_TAIL: tuple[dict[str, object], ...] = (
    _spine(
        "lifecycle.finally",
        {"boundary": "terminal_driver", "outcome": "success", "trace_id": "trace_1a60d32e11f8"},
        event_id="run_eed09c1df112:1034",
        ts="2026-09-16T16:29:01.126899+00:00",
    ),
    _publisher("failed", event_id="run_eed09c1df112:1035"),
    _spine(
        "agent_loop.iteration.end",
        {
            "iteration_kind": "fresh",
            "outcome": "success",
            "role": "solo",
            "trace_id": "trace_1a60d32e11f8",
        },
        event_id="run_eed09c1df112:1039",
        ts="2026-09-16T16:29:01.155893+00:00",
    ),
    _run_stop("failure", event_id="run_eed09c1df112:1040"),
)

# 同一 run 的真实 phase 上下文(payload 裁剪到 fold 读取的字段),让
# "有 phase 即 completed" 的兜底启发式无法掩盖终态判定。
_REAL_CONTEXT: tuple[dict[str, object], ...] = (
    _spine(
        "phase.perceive.fold",
        {"state_id": "trace_1a60d32e11f8"},
        event_id="run_eed09c1df112:19",
        ts="2026-09-16T16:28:35.164784+00:00",
    ),
    _spine(
        "llm.request.header",
        {"reason": "initial", "step_id": "step-001"},
        event_id="run_eed09c1df112:68",
        ts="2026-09-16T16:28:35.218301+00:00",
    ),
    _spine(
        "phase.think.fold",
        {"objective_kind": "user_text", "phase": "think", "summary": "started"},
        event_id="run_eed09c1df112:69",
        ts="2026-09-16T16:28:35.219551+00:00",
    ),
)


def test_real_failed_run_tail_folds_to_failed() -> None:
    """现场 4 条尾序逐字折成 ``failed``。"""
    doc = fold_step_tree([*_REAL_CONTEXT, *_REAL_TAIL], run_id=RUN_ID)
    assert doc.metadata.outcome == "failed"


def test_tail_without_publisher_evidence_still_folds_to_failed() -> None:
    """去掉 ``runtime.event_publisher.publish``(唯一偶然救场者)后仍判 failed。

    修前:``lifecycle.finally`` 无人能覆盖,phase 兜底启发式把失败 run 折成
    ``completed``。
    """
    events = [
        *_REAL_CONTEXT,
        _REAL_TAIL[0],
        _REAL_TAIL[2],
        _REAL_TAIL[3],
    ]
    doc = fold_step_tree(events, run_id=RUN_ID)
    assert doc.metadata.outcome == "failed"


def test_kernel_run_stop_failure_alone_folds_to_failed() -> None:
    """``kernel.run.stop outcome="failure"`` 单独到达即 ``failed``。"""
    doc = fold_step_tree([_run_stop("failure")], run_id=RUN_ID)
    assert doc.metadata.outcome == "failed"


def test_kernel_run_stop_success_alone_folds_to_completed() -> None:
    """成功 run 尾:``kernel.run.stop outcome="success"`` → ``completed``。"""
    doc = fold_step_tree([_run_stop("success")], run_id=RUN_ID)
    assert doc.metadata.outcome == "completed"


def test_kernel_run_stop_cancelled_alone_folds_to_stopped() -> None:
    """取消 run 尾:carrier 发 ``cancelled`` → journal 词表 ``stopped``。"""
    doc = fold_step_tree([_run_stop("cancelled")], run_id=RUN_ID)
    assert doc.metadata.outcome == "stopped"


def test_lifecycle_finally_does_not_stamp_terminal_outcome() -> None:
    """``lifecycle.finally`` 只报 teardown 边界,不得盖 run 终态。"""
    spine_shaped = _spine(
        "lifecycle.finally",
        {"boundary": "terminal_driver", "outcome": "success", "trace_id": "trace_1a60d32e11f8"},
        event_id="run:1034",
        ts="2026-09-16T16:29:01.126899+00:00",
    )
    assert fold_step_tree([spine_shaped], run_id=RUN_ID).metadata.outcome == "in_progress"

    # EventRecord 形态(outcome 在顶层)同样不得盖终态。
    record_shaped = {
        "execution_point": "lifecycle.finally",
        "payload": {"boundary": "terminal_driver"},
        "outcome": "success",
        "when": 0.0,
    }
    assert fold_step_tree([record_shaped], run_id=RUN_ID).metadata.outcome == "in_progress"


def test_unrecognized_kernel_run_stop_outcome_folds_to_failed() -> None:
    """权威事件出现词表外 outcome → ``failed``,不静默穿过。"""
    assert fold_step_tree([_run_stop("exploded")], run_id=RUN_ID).metadata.outcome == "failed"
    assert fold_step_tree([_run_stop(None)], run_id=RUN_ID).metadata.outcome == "failed"


def test_kernel_run_stop_authority_beats_later_evidence() -> None:
    """权威优先于到达顺序:晚到的 publish 证据不得覆盖 ``kernel.run.stop``。"""
    events = [
        _run_stop("failure", event_id="run:1"),
        _publisher("completed", event_id="run:2"),
    ]
    doc = fold_step_tree(events, run_id=RUN_ID)
    assert doc.metadata.outcome == "failed"


def test_publisher_evidence_folds_without_kernel_run_stop() -> None:
    """无权威事件时(resume 路径不发 ``kernel.run.stop``)证据仍生效。"""
    doc = fold_step_tree([_publisher("failed")], run_id=RUN_ID)
    assert doc.metadata.outcome == "failed"
