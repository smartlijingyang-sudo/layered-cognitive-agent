"""EvidenceStore.sweep_orphan 幂等性(ADR-0065 PR-2 / §四)。

- ledger 引用的对象不被清
- 不被引用的对象被清
- 重复调用同 ledger_index 返回 0
- 残留 staging 临时文件被视为孤儿
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.evidence import (
    Classification,
    RetentionClass,
)
from lca.infrastructure.observability.evidence.store import FilesystemEvidenceStore


def test_sweep_keeps_referenced_removes_unreferenced(tmp_path: Path) -> None:
    store = FilesystemEvidenceStore(root=tmp_path)
    keep_receipt = store.prepare(
        b"keep-me",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    drop_receipt = store.prepare(
        b"drop-me",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )

    removed = store.sweep_orphan(
        {"run-1": {keep_receipt.ref}},
    )
    assert removed == 1
    # keep 仍在
    assert store.contains(keep_receipt.ref)
    # drop 已清
    assert not store.contains(drop_receipt.ref)


def test_sweep_is_idempotent(tmp_path: Path) -> None:
    store = FilesystemEvidenceStore(root=tmp_path)
    receipt = store.prepare(
        b"idempotent",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    ledger = {"run-x": {receipt.ref}}

    first = store.sweep_orphan(ledger)
    second = store.sweep_orphan(ledger)
    third = store.sweep_orphan({})  # 空 ledger 也应清掉一切

    assert first == 0
    assert second == 0
    assert third == 1
    assert not store.contains(receipt.ref)


def test_sweep_removes_staging_leftovers(tmp_path: Path) -> None:
    """模拟 prepare 中途崩了,残留 staging 临时文件 —— sweep 必须清。"""
    store = FilesystemEvidenceStore(root=tmp_path)
    alg_dir = tmp_path / "sha256"
    alg_dir.mkdir(parents=True, exist_ok=True)
    orphan_staging = alg_dir / ".staging-99999-deadbeef"
    orphan_staging.write_bytes(b"stale")

    removed = store.sweep_orphan({})
    assert removed == 1
    assert not orphan_staging.exists()


def test_sweep_handles_multiple_runs(tmp_path: Path) -> None:
    """同一 digest 被多 run 引用时,任一 run 引用即保留。"""
    store = FilesystemEvidenceStore(root=tmp_path)
    receipt = store.prepare(
        b"shared",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    ledger = {
        "run-a": {receipt.ref},
        "run-b": {receipt.ref},
    }
    removed = store.sweep_orphan(ledger)
    assert removed == 0
    assert store.contains(receipt.ref)


def test_sweep_empty_ledger_clears_everything(tmp_path: Path) -> None:
    store = FilesystemEvidenceStore(root=tmp_path)
    receipts = [
        store.prepare(
            f"p-{i}".encode(),
            classification=Classification.INTERNAL,
            retention=RetentionClass.RUN_DEFAULT,
        )
        for i in range(3)
    ]
    removed = store.sweep_orphan({})
    assert removed == 3
    for r in receipts:
        assert not store.contains(r.ref)
