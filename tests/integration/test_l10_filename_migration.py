"""ADR-0169 PR-27 L10 filename migration 集成测试。

L10 / D9:spine 默认文件名由 ``events.jsonl`` 迁移到 ``<run_id>.spine.jsonl``。
本测试验证:
1. 新默认 sink 落 ``<run_id>.spine.jsonl``(template + run_id 实例化);
2. 旧 ``events.jsonl`` 文件仍可被新代码 bootstrap(read 透明);
3. 两者同时存在时,优先 ``<run_id>.spine.jsonl``(L10 单写 / 不混读)。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.observability.journal.backends.filesystem import (
    FilesystemJournalStore,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.spine.sinks.routing_file_sink import (
    RunRoutingFileSink,
)


def _make_record(seq: int, run_id: str, *, ep: str = "kernel.run.start") -> dict:
    """Build a JSON-serializable spine record body."""
    return {
        "execution_point": ep,
        "channel": "control",
        "span_id": f"sp-{seq:08d}",
        "parent_span_id": None,
        "sequence": seq,
        "epoch": 1,
        "causality_id": f"causality-{seq:08d}",
        "outcome": None,
        "when": "2026-09-02T00:00:00+00:00",
        "when_corrected": "2026-09-02T00:00:00+00:00",
        "prev_event_hash": None,
        "run_id": run_id,
        "step_id": None,
        "payload": {"marker": "l10_migration", "seq": seq},
        "phase": "live",
        "reason": None,
    }


def test_default_filename_is_spine_jsonl(tmp_path: Path) -> None:
    """新默认:FileSink 落 ``<run_id>.spine.jsonl``,而非 ``events.jsonl``。

    ADR-0169 PR-27 L10 / D9:spine 默认文件名从 ``events.jsonl`` 迁移到
    ``<run_id>.spine.jsonl``(模板 ``$run_id.spine.jsonl`` 实例化)。
    """
    run_id = "run_default_spine"
    sink = FileSink(tmp_path, run_id=run_id)
    spine = EventSpine(sinks=[sink], run_id=run_id)

    spine.append(
        execution_point="kernel.run.start",
        channel="control",
        caller_payload={"marker": "default_spine_filename"},
        outcome=None,
    )
    spine.flush()
    spine.close()
    sink.close()

    # 落点 = <run_id>.spine.jsonl
    assert sink.path.name == f"{run_id}.spine.jsonl"
    assert sink.path.exists()

    # events.jsonl 不应被默认创建
    legacy = tmp_path / "events.jsonl"
    assert not legacy.exists(), "L10 violation: 默认 sink 不应再创建 events.jsonl"

    # 落点内容包含刚才 append 的事件
    lines = [ln for ln in sink.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "kernel.run.start"
    assert obj["run_id"] == run_id


def test_legacy_events_jsonl_no_longer_loaded(tmp_path: Path) -> None:
    """PR-4 收口:旧 ``events.jsonl`` 文件不再被 bootstrap(不再透明兼容)。

    run 目录下只有旧 ``events.jsonl`` 时,新 FilesystemJournalStore:
    - 默认 ``self._path`` 指向 ``<run_id>.spine.jsonl``(新写入将落此);
    - bootstrap 不再 fallback 旧 layout → ``self._events`` 为空;
    - 旧 ledger 数据由 importer 一次性迁移(已迁移完毕),reader 不再透明兜底。
    """
    run_id = "run_legacy_only"
    root = tmp_path / run_id
    legacy = root / "events.jsonl"
    legacy.parent.mkdir(parents=True, exist_ok=True)

    # 预先写一条旧 ledger 数据
    legacy.write_text(
        json.dumps(
            {
                "seq": 1,
                "ts": 1.0,
                "event_type": "KernelRunStart",
                "schema_version": 2,
                "scope": {"trace_id": "t1", "run_id": run_id},
                "data": {"legacy": True, "ignorable": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    store = FilesystemJournalStore(root, run_id=run_id)
    # 新默认写入目标 = <run_id>.spine.jsonl
    assert store.path.name == f"{run_id}.spine.jsonl"
    # 旧 events.jsonl 仍存在(未被破坏)
    assert legacy.exists()
    # PR-4 收口:旧 ledger 不再被 bootstrap 进内存
    assert len(store.events()) == 0

    # 后续 append 写到 <run_id>.spine.jsonl(新默认)
    from lca.contracts.models.observability.journal import (
        JournalEvent,
        RunScope,
        StampedEvent,
    )

    stamped = StampedEvent(
        seq=2,
        ts=2.0,
        scope=RunScope(trace_id="t1", run_id=run_id),
        event=JournalEvent(),
        event_type="KernelRunStop",
        data={"fresh": True},
    )
    store.append(stamped)

    # 新写入落在 spine.jsonl,events.jsonl 保持只读
    spine_path = root / f"{run_id}.spine.jsonl"
    assert spine_path.exists()
    assert legacy.exists()

    spine_lines = spine_path.read_text(encoding="utf-8").splitlines()
    assert any("KernelRunStop" in ln for ln in spine_lines)


def test_spine_jsonl_preferred_when_both_exist(tmp_path: Path) -> None:
    """两者同时存在时,优先 ``<run_id>.spine.jsonl``(L10 单写防混读)。

    当 run 目录里 ``events.jsonl`` 与 ``<run_id>.spine.jsonl`` 同时存在,
    FilesystemJournalStore bootstrap 阶段优先读 ``<run_id>.spine.jsonl``,
    不会把旧 ledger 数据混入新 ledger。
    """
    run_id = "run_both"
    root = tmp_path / run_id
    root.mkdir(parents=True, exist_ok=True)

    # 旧 ledger:events.jsonl 写入 1 条 legacy 事件
    legacy = root / "events.jsonl"
    legacy.write_text(
        json.dumps(
            {
                "seq": 1,
                "ts": 1.0,
                "event_type": "LegacyEvent",
                "schema_version": 2,
                "scope": {"trace_id": "t1", "run_id": run_id},
                "data": {"from": "legacy", "ignorable": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # 新 ledger:<run_id>.spine.jsonl 写入 1 条 spine 事件
    spine_path = root / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "seq": 1,
                "ts": 2.0,
                "event_type": "SpineEvent",
                "schema_version": 2,
                "scope": {"trace_id": "t1", "run_id": run_id},
                "data": {"from": "spine", "ignorable": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    store = FilesystemJournalStore(root, run_id=run_id)
    # bootstrap 优先读 spine.jsonl,events.jsonl 被忽略
    assert store.path.name == f"{run_id}.spine.jsonl"
    assert len(store.events()) == 1
    assert store.events()[0].event_type == "SpineEvent"


def test_routing_sink_per_run_uses_spine_filename(tmp_path: Path) -> None:
    """RunRoutingFileSink 默认 per-run 文件 = ``<run_id>.spine.jsonl``。"""
    sink = RunRoutingFileSink(
        boot_path=tmp_path / "boot-events.jsonl",
        runs_root=tmp_path / "runs",
    )

    # path_for 返回 spine 命名
    p = sink.path_for("run_xyz")
    assert p.name == "run_xyz.spine.jsonl"

    sink.close()
