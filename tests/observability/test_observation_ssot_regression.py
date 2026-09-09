"""观测面 SSOT 收口回归测试(2026-09-03 / ADR-0212 收敛)。

覆盖 docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md
根 note 收口的核心修复:

1. ``find_spine_file`` 优先 ``<run_dir>/<run_id>.spine.jsonl``,
   其次 ``<run_dir>/events.jsonl`` 兜底;两者都缺抛 ObservationSSOTError。
2. (已迁出)``step.tool_call.record`` canonical flat payload 恢复 →
   收口进 :mod:`tests.plugins.session.derivers.step_tree.test_fold_deriver_idempotence`
   (ADR-0212 §9)。回归 run_3e48052e6c36 ``tool_call`` 全空。
3. (已迁出)``step.tool_result.record`` canonical flat payload 恢复 →
   同上位置。回归同次 run ``tool_result`` 全空。
4. ``RunOutcomeProjector.failed`` 在异常归一化前自动调用
   ``emit_exception_caught``,把 traceback 落到 ``exception.caught`` spine
   event,而不是只在 ``RunFact.payload["error"]`` 写一行字符串。

每条 test 直接驱动 shipped code, not re-implementation。

注:派生面 fold 路径走 :class:`StepTreeFoldDeriver`(ADR-0212 收口),
见 ``test_fold_deriver_idempotence.py``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.harness.declarative.execute.outcome_projection import RunOutcomeProjector

# ── 1. find_spine_file (ssot.py) ────────────────────────────────────────


def test_find_spine_file_prefers_new_naming(tmp_path: Path) -> None:
    """新 spine 命名(``<run_id>.spine.jsonl``)存在 → 直接返回。"""
    from lca.contracts.observability.core.ssot import find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    new = run_dir / "run_abc.spine.jsonl"
    new.write_text("{}\n", encoding="utf-8")
    legacy = run_dir / "events.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    # 两者并存:必须返回 spine 命名,而不是 legacy(PR-27 约定)。
    assert find_spine_file(run_dir, "run_abc") == new


def test_find_spine_file_legacy_fallback_removed(tmp_path: Path) -> None:
    """PR-4 收口:旧 ``events.jsonl`` 兜底已下线。

    新命名不存在 + legacy 存在 → 抛 ObservationSSOTError(不再 fallback)。
    旧 run 迁移由 importer 一次性完成;不再有 reader 透明兜底。
    """
    from lca.contracts.observability.core.ssot import ObservationSSOTError, find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    legacy = run_dir / "events.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ObservationSSOTError):
        find_spine_file(run_dir, "run_abc")


def test_find_spine_file_missing_both_raises(tmp_path: Path) -> None:
    """两者都缺 → ObservationSSOTError,不是 silent zero。"""
    from lca.contracts.observability.core.ssot import ObservationSSOTError, find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    with pytest.raises(ObservationSSOTError):
        find_spine_file(run_dir, "run_abc")


def test_find_spine_file_missing_run_dir_raises(tmp_path: Path) -> None:
    """run_dir 本身不存在 → ObservationSSOTError,file name 不存在仅是子集。"""
    from lca.contracts.observability.core.ssot import ObservationSSOTError, find_spine_file

    with pytest.raises(ObservationSSOTError):
        find_spine_file(tmp_path / "nope", "run_abc")


# ── 3. RunOutcomeProjector.failed auto-emits exception.caught ───────────


class _CapturingJournal:
    def __init__(self) -> None:
        self.facts: list[object] = []

    def commit_fact(self, fact, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        self.facts.append(fact)
        return fact.fact_id or f"{node_ref}:fact:{len(self.facts)}"

    def commit_evidence(self, evidence_ref, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        return evidence_ref

    def commit_observation(self, observation, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        return f"{node_ref}:observation:1"


def test_outcome_projector_failed_emits_exception_caught(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``RunOutcomeProjector.failed`` 必须先把异常归一化落
    ``exception.caught`` spine event,再 ``commit_fact`` —— 这是
    run_3e48052e6c36 失败时 ``exceptions.jsonl`` 为空的根因修复。

    通过 stub ``emit_exception_caught`` 验证被调用 + payload 携带
    ``traceback_text``。
    """
    from lca.harness.graph.traversal import PhaseTraversal

    journal = _CapturingJournal()
    captured: list[dict] = []

    def _fake_safe_append(*, execution_point, channel, payload=None, outcome=None):  # type: ignore[no-untyped-def]
        # payload 是 record.asdict() 展开后的 dict
        captured.append(payload)
        return None

    monkeypatch.setattr(
        "lca.infrastructure.observability.spine.exception_emit._safe_append",
        _fake_safe_append,
    )

    projector = RunOutcomeProjector(
        journal,  # type: ignore[arg-type]
        run_id="run_test",
        trace_id="trace_test",
        boundary="declarative.interpreter._drive",
    )
    traversal = PhaseTraversal.start(
        plan_ref="plan_x",
        entry_node_id="node_x",
        artifacts={},
        input=None,
    )
    state = AgentState(
        trace_id="trace_test",
        task="t",
        budget=Budget(),
        extra={"run_id": "run_test"},
    )

    err = RuntimeError("PG-007: node visit budget exhausted: perceive.main")
    projector.failed(
        err,
        traversal=traversal,
        state=state,
        plan_ref="plan_x",
        visits=[],
        facts=[],
        reason="validation_error",
        error_code="PG-007",
    )

    # 必须归一化并落 exception.caught。
    assert captured, "exception.caught was not emitted"
    payload = captured[0]
    assert payload["exception_class"].endswith("RuntimeError")
    assert "PG-007" in payload["exception_message"]
    assert payload["traceback_text"], "traceback_text must be populated"
    assert payload["run_id"] == "run_test"
    assert payload["trace_id"] == "trace_test"
    assert payload["boundary"].startswith("declarative.interpreter._drive")

    # RunFact 也必须带 traceback 字符串,作为 sidecar 失败的次级兜底。
    run_failed = next(f for f in journal.facts if getattr(f, "kind", "") == "run.failed")
    assert run_failed.payload["traceback"], "traceback must be on RunFact"
    assert "PG-007" in run_failed.payload["traceback"]


