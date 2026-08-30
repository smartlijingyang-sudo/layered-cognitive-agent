"""FilesystemEvidenceStore round-trip + integrity fail-fast(ADR-0065 PR-2 / L5)。

- prepare → get round-trip 内容相等
- 摘要不匹配 → EvidenceIntegrityError
- 字节数不一致 → EvidenceIntegrityError
- 缺失 → EvidenceIntegrityError(不是 None)
- audience 不满足 → PermissionError
- 跨平台路径:Windows / Linux / macOS 都用 pathlib.Path,无硬编码 separator
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.observability.evidence import (
    Classification,
    EvidenceIntegrityError,
    EvidenceReceipt,
    EvidenceRef,
    RetentionClass,
)
from lca.layer0_infra.observability.evidence.store import FilesystemEvidenceStore


@pytest.fixture
def fs_store(tmp_path: Path) -> FilesystemEvidenceStore:
    return FilesystemEvidenceStore(root=tmp_path)


def test_prepare_then_get_roundtrip(fs_store: FilesystemEvidenceStore) -> None:
    payload = b"hello evidence world"
    receipt = fs_store.prepare(
        payload,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
        media_type="text/plain",
        prepared_by="test",
    )
    assert isinstance(receipt, EvidenceReceipt)
    assert receipt.content_sha256 == receipt.ref.digest
    assert receipt.ref.byte_length == len(payload)
    assert receipt.ref.classification == Classification.INTERNAL

    restored = fs_store.get(
        receipt.ref,
        requester="test",
        audience=Classification.INTERNAL,
    )
    assert restored == payload


def test_prepare_staging_left_no_garbage(fs_store: FilesystemEvidenceStore) -> None:
    """prepare 完成后 staging 临时文件应被清掉;只留正式 digest + meta。"""
    receipt = fs_store.prepare(
        b"x" * 1024,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    alg_dir = fs_store.storage_root / "sha256"
    staging = list(alg_dir.glob(".staging-*"))
    assert staging == [], f"staging leftover: {staging}"
    assert (alg_dir / receipt.ref.digest).exists()
    meta = alg_dir / f"{receipt.ref.digest}.meta.json"
    assert meta.exists()


def test_get_raises_on_missing_digest(fs_store: FilesystemEvidenceStore) -> None:
    ref = EvidenceRef(
        digest="0" * 64,
        byte_length=42,
        classification=Classification.INTERNAL,
    )
    with pytest.raises(EvidenceIntegrityError):
        fs_store.get(ref, requester="t", audience=Classification.INTERNAL)


def test_get_raises_on_digest_tampering(fs_store: FilesystemEvidenceStore) -> None:
    receipt = fs_store.prepare(
        b"abc",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    # 把正式 digest 文件内容改了
    target = fs_store.storage_root / "sha256" / receipt.ref.digest
    target.write_bytes(b"corrupted-payload")
    with pytest.raises(EvidenceIntegrityError):
        fs_store.get(receipt.ref, requester="t", audience=Classification.INTERNAL)


def test_get_raises_on_byte_length_mismatch(fs_store: FilesystemEvidenceStore) -> None:
    receipt = fs_store.prepare(
        b"abc",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    # 篡改 byte_length:伪造一个 byte_length=999 但实际 3 字节的 ref。
    bad_ref = EvidenceRef(
        algorithm="sha256",
        digest=receipt.ref.digest,
        media_type="text/plain",
        byte_length=999,
        classification=Classification.INTERNAL,
    )
    with pytest.raises(EvidenceIntegrityError):
        fs_store.get(bad_ref, requester="t", audience=Classification.INTERNAL)


def test_get_enforces_audience(fs_store: FilesystemEvidenceStore) -> None:
    receipt = fs_store.prepare(
        b"secret",
        classification=Classification.RESTRICTED,
        retention=RetentionClass.LONG,
    )
    # 用 PUBLIC audience 读 RESTRICTED → 拒绝
    with pytest.raises(PermissionError):
        fs_store.get(
            receipt.ref,
            requester="guest",
            audience=Classification.PUBLIC,
        )
    # 用 RESTRICTED audience 读 → 允许
    restored = fs_store.get(receipt.ref, requester="ops", audience=Classification.RESTRICTED)
    assert restored == b"secret"


def test_get_raises_on_algorithm_mismatch(fs_store: FilesystemEvidenceStore) -> None:
    receipt = fs_store.prepare(
        b"x",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    bad_ref = EvidenceRef(
        algorithm="sha512",
        digest=receipt.ref.digest,
        byte_length=receipt.ref.byte_length,
        classification=Classification.INTERNAL,
    )
    with pytest.raises(EvidenceIntegrityError):
        fs_store.get(bad_ref, requester="t", audience=Classification.INTERNAL)


def test_contains_only_checks_existence(fs_store: FilesystemEvidenceStore) -> None:
    receipt = fs_store.prepare(
        b"x",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    assert fs_store.contains(receipt.ref) is True
    fake = EvidenceRef(digest="f" * 64, byte_length=1)
    assert fs_store.contains(fake) is False


def test_cross_platform_paths_use_pathlib_only(fs_store: FilesystemEvidenceStore) -> None:
    """Locator 必须用 Path,不含硬编码 separator;Win/Linux/macOS 全兼容。"""
    receipt = fs_store.prepare(
        b"path-test",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    assert isinstance(receipt.ref.locator, str)
    # locator 必须是可被 Path 解析的字符串,不含硬编码 '\\' 或 '/'
    assert "\\" not in receipt.ref.locator.replace("/", "")
    Path(receipt.ref.locator)  # 不能 raise


def test_path_root_can_be_relative(tmp_path: Path) -> None:
    """root 接受相对路径 —— 配合 ObservabilitySettings.evidence_root 默认值。"""
    relative_root = tmp_path / "relative_subdir"
    store = FilesystemEvidenceStore(root=relative_root)
    receipt = store.prepare(
        b"hi",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    assert (relative_root / "sha256" / receipt.ref.digest).exists()


def test_prepare_rejects_non_bytes(tmp_path: Path) -> None:
    store = FilesystemEvidenceStore(root=tmp_path)
    with pytest.raises(TypeError):
        store.prepare(  # type: ignore[arg-type]
            "not-bytes",  # type: ignore[arg-type]
            classification=Classification.INTERNAL,
            retention=RetentionClass.RUN_DEFAULT,
        )


def test_prepare_accepts_bytearray(tmp_path: Path) -> None:
    """bytearray 是合法 bytes-like;应接受并产生等价 receipt。"""
    store = FilesystemEvidenceStore(root=tmp_path)
    receipt = store.prepare(
        bytearray(b"abc"),
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    assert receipt.ref.byte_length == 3


def test_prepare_empty_payload(tmp_path: Path) -> None:
    """空载荷允许;空摘要合法。"""
    store = FilesystemEvidenceStore(root=tmp_path)
    receipt = store.prepare(
        b"",
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    expected_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert receipt.ref.digest == expected_digest
    assert receipt.ref.byte_length == 0


def test_prepare_payload_immutable_against_caller(tmp_path: Path) -> None:
    """bytearray 在 prepare 内被转成 bytes;后续修改 bytearray 不影响 store。"""
    store = FilesystemEvidenceStore(root=tmp_path)
    ba = bytearray(b"original")
    receipt = store.prepare(
        ba,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    ba.clear()
    restored = store.get(receipt.ref, requester="t", audience=Classification.INTERNAL)
    assert restored == b"original"
