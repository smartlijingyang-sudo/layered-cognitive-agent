"""ADR-0164 Phase 7 端到端回归: ``build_step_lifecycle_store`` → ``create_run_components`` → ``close_and_finalize`` 完整闭环。

回归点(原始 bug):
    - ``create_run_components`` 通过 ContextVar 拿 lifecycle_store, 生产代码
      从未 ``set_lifecycle_store`` —— 导致 ``StepGroupedBackend`` 永远是 None,
      ``journal.json`` 从未落盘, doctor H2 失败, ``traces/runs/<run_id>/``
      目录里只有 manifest + profile_snapshot。

修复后应满足的不变量:
    1. ``build_step_lifecycle_store`` 立即得到一个已 ``bind_run`` 的 store;
       ``store.document.metadata.agent_role / objective`` 与入参一致。
    2. 把 store 注入 ``create_run_components`` 后, ``components.step_tree_writer``
       不再为 None(它的 ``backend.lifecycle_store`` 是同一个 store)。
    3. terminalize 调 ``store.close_and_finalize()`` 拿 document → 走
       ``StepGroupedProjector.write()`` → 磁盘上产生 ``journal.json``,
       schema 是 ``lca.journal/3``, 包含 1 个 step。
    4. ``close_and_finalize`` 是 idempotent —— 第二次调不会抛, 也不会重写
       closed_at(timestamp 一致)。
    5. 没有 store 注入(offline 脚本)时回退到 ContextVar 路径(老 unit 测不破)。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability.journal_doc import JournalMetadata
from lca.contracts.models.observability.journal_step import (
    ThinkingTrace,
)
from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.plugins.seams.observability.run_ledger import FilesystemRunLedgerFactory
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_lifecycle_store


def _metadata_input() -> BuildJournalMetadata:
    return BuildJournalMetadata(
        agent_role="solo",
        strategy_key="solo",
        plan_ref="plan_test_journal_binding",
        objective="end-to-end journal binding regression",
    )


def test_build_step_lifecycle_store_binds_metadata(tmp_path: Path) -> None:
    store = build_step_lifecycle_store(
        run_id="run_test_bind",
        trace_id="trace_test_bind",
        metadata=_metadata_input(),
    )
    assert store.run_id == "run_test_bind"
    assert store.trace_id == "trace_test_bind"
    assert store.document is not None
    assert isinstance(store.document.metadata, JournalMetadata)
    assert store.document.metadata.agent_role == "solo"
    assert store.document.metadata.strategy_key == "solo"
    assert store.document.metadata.plan_ref == "plan_test_journal_binding"
    assert store.document.metadata.objective == "end-to-end journal binding regression"
    assert store.document.metadata.outcome == "in_progress"


def test_create_run_components_with_injected_store_produces_backend(tmp_path: Path) -> None:
    factory = FilesystemRunLedgerFactory(tmp_path, fsync_each_append=True)
    lifecycle_store = build_step_lifecycle_store(
        run_id="run_injected",
        trace_id="trace_injected",
        metadata=_metadata_input(),
    )
    components = factory.create_run_components(
        jsonl_path=tmp_path / "run_injected" / "journal.jsonl",
        lifecycle_store=lifecycle_store,
    )
    bundle = components.step_tree_writer
    assert bundle is not None, "step_tree_bundle 必须是 StepGroupedBundle, 不能 None"
    backend = getattr(bundle, "backend", None)
    assert isinstance(backend, StepGroupedBackend), (
        f"backend 必须是 StepGroupedBackend, 得到 {type(backend).__name__}"
    )
    assert backend.lifecycle_store is lifecycle_store
    assert backend.output_path == tmp_path / "run_injected" / "journal.json"


def test_create_run_components_without_injected_store_falls_back_to_contextvar(
    tmp_path: Path,
) -> None:
    """不传 lifecycle_store 时不应硬错, 而是 ContextVar 兜底(老路径兼容)。"""
    from lca.runtime import step_lifecycle

    factory = FilesystemRunLedgerFactory(tmp_path, fsync_each_append=True)
    fallback_store = build_step_lifecycle_store(
        run_id="run_fallback",
        trace_id="trace_fallback",
        metadata=_metadata_input(),
    )
    token = step_lifecycle.set_lifecycle_store(fallback_store)
    try:
        components = factory.create_run_components(
            jsonl_path=tmp_path / "run_fallback" / "journal.jsonl",
        )
        bundle = components.step_tree_writer
        assert bundle is not None
        backend = getattr(bundle, "backend", None)
        assert isinstance(backend, StepGroupedBackend)
        assert backend.lifecycle_store is fallback_store
    finally:
        step_lifecycle.reset_lifecycle_store(token)


def test_close_and_finalize_persists_journal_json(tmp_path: Path) -> None:
    """最小端到端: store → open_step → record_thinking → close_step →
    close_and_finalize → StepGroupedBackend.flush → journal.json 落盘。
    """
    factory = FilesystemRunLedgerFactory(tmp_path, fsync_each_append=True)
    run_id = "run_e2e_persist"
    lifecycle_store = build_step_lifecycle_store(
        run_id=run_id,
        trace_id="trace_e2e_persist",
        metadata=_metadata_input(),
    )
    components = factory.create_run_components(
        jsonl_path=tmp_path / run_id / "journal.jsonl",
        lifecycle_store=lifecycle_store,
    )
    bundle = components.step_tree_writer
    assert bundle is not None

    # 开 step + record + close
    step = lifecycle_store.open_step("think")
    lifecycle_store.record_thinking(
        ThinkingTrace(
            model="gpt-test",
            latency_ms=12,
            reasoning="test reasoning",
            decision="respond",
        )
    )
    lifecycle_store.close_step("ok")

    # final 落盘
    document = lifecycle_store.close_and_finalize(outcome="completed")
    assert document is not None
    assert document.closed_at is not None
    assert len(document.steps) == 1
    assert document.steps[0].step_id == step.step_id

    # 写盘
    bundle.backend.flush()
    journal_path = tmp_path / run_id / "journal.json"
    assert journal_path.exists(), "journal.json 必须落盘"

    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "lca.journal/3"
    assert payload["run_id"] == run_id
    assert payload["metadata"]["agent_role"] == "solo"
    assert payload["metadata"]["plan_ref"] == "plan_test_journal_binding"
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["outcome"] == "ok"
    assert payload["metadata"]["closed_at"] is not None


def test_close_and_finalize_is_idempotent(tmp_path: Path) -> None:
    lifecycle_store = build_step_lifecycle_store(
        run_id="run_idempotent",
        trace_id="trace_idempotent",
        metadata=_metadata_input(),
    )
    lifecycle_store.open_step("think")
    lifecycle_store.close_step("ok")

    first = lifecycle_store.close_and_finalize(outcome="completed")
    assert first is not None
    assert first.closed_at is not None
    closed_at_first = first.closed_at

    # 第二次: idempotent, 不抛, closed_at 不变
    second = lifecycle_store.close_and_finalize(outcome="failed")
    assert second is not None
    assert second.closed_at == closed_at_first, (
        "重复 finalize 不应改写 closed_at —— 否则 journal.json 会被改写产生新时间戳"
    )


def test_close_and_finalize_recovers_dangling_step(tmp_path: Path) -> None:
    """open_step 但没 close_step → close_and_finalize 必须能 finalize,
    不能让 document 卡在 open 状态。"""
    lifecycle_store = build_step_lifecycle_store(
        run_id="run_dangling",
        trace_id="trace_dangling",
        metadata=_metadata_input(),
    )
    draft = lifecycle_store.open_step("think")
    assert lifecycle_store.get_current_step() is draft

    # 不 close, 直接 finalize —— 必须能 finalize, 且把 step 以 fail 闭合
    document = lifecycle_store.close_and_finalize(outcome="stopped")
    assert document is not None
    assert document.closed_at is not None
    assert len(document.steps) == 1
    assert document.steps[0].outcome == "fail", (
        "dangling open step 必须以 fail 闭合(不能 ok —— 暗示成功)"
    )
