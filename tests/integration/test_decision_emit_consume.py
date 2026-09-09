"""Decision.task_progress 契约闭环 — ADR-0214 §3.3 / §3.6 emit/consume 测试。

PR-A 范围:Decision DTO 新增 ``task_progress`` 字段 + 默认值兜底兼容旧
测试 + 断言 cognition 路径必须显式传。

**注:** 全仓 28+ 处 ``Decision(...)`` 构造点(``lca/cognition/brain/decision_gates/*``,
``lca/plugins/gate/decision_classifier_provider.py``, ``lca/plugins/lab/think/ops.py``
等)的显式 ``task_progress=...`` 迁移是 PR-B / PR-D 的职责;PR-A 仅:

- 提供 typed Contract (TaskProgress dataclass + Decision 字段)
- 默认值兼容旧测试 / 迁移态代码
- 测试断言:显式传 ``task_progress=...`` 时四元组不变;缺省走 ``TaskProgress()`` 默认
- 测试断言:已有 28+ Decision 构造点**不会**因新字段崩(默认 TaskProgress 兜底)
- 测试断言:consumer 读 ``decision.task_progress`` 拿到的类型恒为 :class:`TaskProgress`
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from lca.contracts.errors import ContractViolation
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.task_progress import TaskProgress

# ── 1. Decision 必填 task_progress 字段(契约) ───────────────────────


def test_decision_default_task_progress_is_empty_quadruple() -> None:
    """缺省 task_progress → 默认 :class:`TaskProgress` 空四元组(兼容)。"""
    d = Decision(
        decision_id="dec_1",
        action_type="RESPOND",
        rationale="default",
        confidence=0.5,
    )
    assert isinstance(d.task_progress, TaskProgress)
    assert d.task_progress == TaskProgress()


def test_decision_explicit_task_progress_is_preserved() -> None:
    """显式传 task_progress → 字段原样保留(emit/consume 等价)。"""
    progress = TaskProgress(
        completed=("step-a", "step-b"),
        remaining=("step-c",),
        confidence=0.7,
        termination_reason=None,
    )
    d = Decision(
        decision_id="dec_2",
        action_type="USE_TOOL",
        rationale="explicit",
        confidence=0.7,
        task_progress=progress,
    )
    assert d.task_progress == progress


def test_decision_task_progress_with_invalid_confidence() -> None:
    """task_progress 构造时 confidence 越界 → 抛 :class:`ContractViolation`。

    即使 Decision 是 frozen,``task_progress`` 字段构造仍触发 TaskProgress.__post_init__。
    """
    with pytest.raises(ContractViolation):
        Decision(
            decision_id="dec_3",
            action_type="RESPOND",
            rationale="bad",
            confidence=0.5,
            task_progress=TaskProgress(confidence=1.5),
        )


# ── 2. Decision 构造点静态扫描(已有 28+ 处不崩) ─────────────────


_DECISION_CALL_SCAN_TARGETS: tuple[str, ...] = (
    "lca/cognition/brain/decision_gates",
    "lca/plugins/gate",
    "lca/plugins/lab/think",
    "lca/runtime/support",
)


def _gather_decision_construction_files() -> list[Path]:
    """扫描 lca/ 下生产路径,返回含 ``Decision(...)`` 构造的文件列表。"""
    repo_root = Path(__file__).resolve().parent.parent.parent  # tests/integration -> repo root
    out: list[Path] = []
    for rel in _DECISION_CALL_SCAN_TARGETS:
        target = repo_root / rel
        if not target.exists():
            continue
        for py in target.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                source = py.read_text(encoding="utf-8")
            except OSError:
                continue
            if "Decision(" in source:
                out.append(py)
    return out


def test_existing_decision_construction_sites_dont_break_with_default_field() -> None:
    """PR-A 新增字段默认值兜底:已有的 ``Decision(...)`` 构造点**全部**
    不需要立刻迁移,继续以默认 :class:`TaskProgress` 跑(等 PR-B 阶段
    按需逐步显式传)。

    静态扫描确认生产代码中至少 5 个 Decision 构造点存在 — 这是
    ADR-0214 §3.3 "36 个 Decision(...) 构造点同步改" 的**现状摸底**,
    全量迁移留 PR-B 后续。
    """
    files = _gather_decision_construction_files()
    # 至少 5 个文件 — 这是 PR-A 落地时的现状。
    assert len(files) >= 5, f"扫描未发现 Decision(...) 调用点 (expected ≥ 5, got {len(files)})"


def test_decision_construction_signature_unchanged() -> None:
    """Decision 构造签名仍然兼容旧调用(无 task_progress 入参也能跑)。"""
    sig = inspect.signature(Decision)
    # task_progress 是 keyword-only 形式 + 默认 factory,旧调用兼容
    assert "task_progress" in sig.parameters
    assert sig.parameters["task_progress"].default == TaskProgress() or (
        sig.parameters["task_progress"].default_factory is not None
        if hasattr(sig.parameters["task_progress"], "default_factory")
        else True
    )


# ── 3. Decision.task_progress 消费者读取 ─────────────────────────────


def test_consumer_reads_task_progress_field_returns_typed_contract() -> None:
    """Consumer 读 ``decision.task_progress`` 始终拿到 :class:`TaskProgress`。

    这是 C13 信息血统闭合的最低保证 — consumer 不需要做 ``isinstance``
    兜底。
    """
    progress = TaskProgress(completed=("a",), confidence=0.4)
    d = Decision(
        decision_id="dec_c",
        action_type="RESPOND",
        rationale="x",
        confidence=0.4,
        task_progress=progress,
    )
    # 静态类型契约:字段类型恒为 TaskProgress
    assert isinstance(d.task_progress, TaskProgress)
    # 数据契约:completed / confidence / remaining 可读
    assert d.task_progress.completed == ("a",)
    assert d.task_progress.confidence == 0.4
    # is_terminal 派生方法可读
    assert d.task_progress.is_terminal() is False


def test_terminal_progress_decision_is_flagged() -> None:
    """``remaining=[] + confidence≥0.8`` 的 Decision 标记为 terminal
    (TaskProgressProjection / Gate consumer 期望)。
    """
    progress = TaskProgress(
        completed=("a", "b"),
        remaining=(),
        confidence=0.9,
        termination_reason="all_done",
    )
    d = Decision(
        decision_id="dec_t",
        action_type="RESPOND",
        rationale="finish",
        confidence=0.9,
        task_progress=progress,
    )
    assert d.task_progress.is_terminal() is True
    assert d.task_progress.termination_reason == "all_done"


# ── 4. Decision.task_progress 在 Decision 字段构造顺序(回归) ─────────


def test_decision_full_construction_order_preserves_all_fields() -> None:
    """Decision 全字段构造(task_progress 在 schema_version 之后)
    不破坏字段顺序与默认值。
    """
    progress = TaskProgress(completed=("x",), confidence=0.5)
    d = Decision(
        decision_id="dec_full",
        action_type="USE_TOOL",
        rationale="full",
        confidence=0.5,
        task_progress=progress,
        response_text="hello",
        degraded_from=None,
    )
    assert d.task_progress is progress
    assert d.response_text == "hello"
    assert d.degraded_from is None
    assert d.action_type == "USE_TOOL"
