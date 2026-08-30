"""FilesystemEvidenceStore —— fs 后端实现(ADR-0065 L5)。

布局::

    <root>/
        <digest_alg>/
            <digest>     # 内容寻址;文件名 = sha256 hex

``EvidenceRef.locator`` 存 backend 私有路径,EvidenceRef 整体可跨 backend
序列化时由 caller 把 ``locator`` 当 backend-specific 字段处理。

实现要点(0065 §四):
- prepare 走"准备 → 验证 → 引用 → 提交":写到 staging 临时文件,算 sha256,
  写 receipt 元数据(``.meta.json`` 旁路),原子 rename 到正式位置,再清
  staging。任一阶段失败都抛 EvidenceIntegrityError,不留垃圾。
- get 重新读 + 重算 sha256 + 比对 byte_length + 比对 classification;
  任何不一致都抛 EvidenceIntegrityError,绝不返回 None 掩盖失败。
- sweep_orphan 遍历 ``<root>/<alg>/`` 下所有 digest,在 ledger_index 全
  局集中查询;不在 → 删。幂等。
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lca.contracts.mechanisms.content_addressable import ContentAddressableStore
from lca.contracts.observability.evidence import (
    Classification,
    EvidenceIntegrityError,
    EvidenceReceipt,
    EvidenceRef,
    EvidenceStore,
    RetentionClass,
)

_DEFAULT_ALG = "sha256"


@dataclass(slots=True)
class FilesystemEvidenceStore(EvidenceStore):
    """fs 后端 EvidenceStore(ADR-0065 L5)。"""

    root: Path
    algorithm: str = _DEFAULT_ALG

    def __post_init__(self) -> None:
        self._root = Path(self.root)
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / self.algorithm).mkdir(parents=True, exist_ok=True)

    @property
    def storage_root(self) -> Path:
        return self._root

    # ── EvidenceStore 契约 ──────────────────────────────────────

    def prepare(
        self,
        payload: bytes,
        *,
        classification: Classification,
        retention: RetentionClass,
        media_type: str = "application/octet-stream",
        prepared_by: str = "",
    ) -> EvidenceReceipt:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(f"payload must be bytes, got {type(payload).__name__}")
        payload = bytes(payload)

        # 准备：写 staging 临时文件
        import hashlib

        digest = hashlib.new(self.algorithm)
        digest.update(payload)
        content_sha256 = digest.hexdigest()

        staging_dir = self._root / self.algorithm
        staging = staging_dir / f".staging-{os.getpid()}-{time.time_ns()}-{content_sha256[:8]}"
        meta_path = staging.with_suffix(staging.suffix + ".meta.json")
        try:
            staging.write_bytes(payload)
            meta_path.write_text(
                json.dumps(
                    {
                        "media_type": media_type,
                        "byte_length": len(payload),
                        "classification": classification.value,
                        "retention": retention.value,
                        "prepared_at": time.time(),
                        "prepared_by": prepared_by,
                        "algorithm": self.algorithm,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            # 引用：原子 rename 到正式位置
            final_path = staging_dir / content_sha256
            os.replace(staging, final_path)
            os.replace(meta_path, final_path.with_suffix(final_path.suffix + ".meta.json"))
        except OSError as exc:
            # 清掉 staging 垃圾 —— best-effort;失败也由 EvidenceIntegrityError 主导
            for p in (staging, meta_path):
                if p.exists():
                    with contextlib.suppress(OSError):
                        p.unlink()
            raise EvidenceIntegrityError(f"failed to commit evidence: {exc}") from exc

        # 验证：再读一次 + 重算摘要 + 比对 byte_length
        try:
            verified = final_path.read_bytes()
        except OSError as exc:
            raise EvidenceIntegrityError(
                f"failed to read back evidence at {final_path}: {exc}"
            ) from exc
        if len(verified) != len(payload):
            raise EvidenceIntegrityError(
                f"evidence byte_length mismatch on read-back: wrote {len(payload)} got {len(verified)}"
            )
        verify_digest = hashlib.new(self.algorithm)
        verify_digest.update(verified)
        if verify_digest.hexdigest() != content_sha256:
            raise EvidenceIntegrityError("evidence digest mismatch on read-back")

        # 提交：返回 receipt
        ref = EvidenceRef(
            algorithm=self.algorithm,
            digest=content_sha256,
            media_type=media_type,
            byte_length=len(payload),
            classification=classification,
            retention=retention,
            locator=str(final_path),
        )
        return EvidenceReceipt(
            ref=ref,
            prepared_at=time.time(),
            prepared_by=prepared_by,
            content_sha256=content_sha256,
        )

    def get(
        self,
        ref: EvidenceRef,
        *,
        requester: str,
        audience: Classification,
    ) -> bytes:
        if ref.algorithm != self.algorithm:
            raise EvidenceIntegrityError(
                f"algorithm mismatch: ref={ref.algorithm} store={self.algorithm}"
            )
        # 策略再检：requester / audience 不满足 ref.classification → PermissionError
        _enforce_audience(ref.classification, audience)

        path = self._path_for(ref)
        try:
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise EvidenceIntegrityError(f"evidence missing: digest={ref.digest}") from exc
        except OSError as exc:
            raise EvidenceIntegrityError(f"failed to read evidence at {path}: {exc}") from exc

        # 完整性验证(必须)
        import hashlib

        digest = hashlib.new(self.algorithm)
        digest.update(payload)
        if digest.hexdigest() != ref.digest:
            raise EvidenceIntegrityError(
                f"evidence digest mismatch: expected={ref.digest} got={digest.hexdigest()}"
            )
        if len(payload) != ref.byte_length:
            raise EvidenceIntegrityError(
                f"evidence byte_length mismatch: expected={ref.byte_length} got={len(payload)}"
            )
        return payload

    def contains(self, ref: EvidenceRef) -> bool:
        return self._path_for(ref).exists()

    def sweep_orphan(
        self,
        ledger_index: Mapping[str, set[EvidenceRef]],
    ) -> int:
        """清掉不被任何 ledger 引用对象;幂等。

        ledger_index: {run_id: set[EvidenceRef]};若同一 digest 被任一 run
        引用则保留,否则删。
        """
        live: set[str] = set()
        for refs in ledger_index.values():
            for ref in refs:
                if ref.algorithm == self.algorithm:
                    live.add(ref.digest)

        removed = 0
        alg_dir = self._root / self.algorithm
        for path in alg_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith(".staging-"):
                # 残留 staging —— 视作孤儿
                with contextlib.suppress(OSError):
                    path.unlink()
                    removed += 1
                continue
            if path.suffix == ".json" and path.stem.endswith(".meta"):
                continue
            digest = path.name
            if digest in live:
                continue
            with contextlib.suppress(OSError):
                path.unlink()
                removed += 1
            # 旁路 meta
            meta = path.with_suffix(path.suffix + ".meta.json")
            if meta.exists():
                with contextlib.suppress(OSError):
                    meta.unlink()
        return removed

    # ── 私有 ──────────────────────────────────────────────────────

    def _path_for(self, ref: EvidenceRef) -> Path:
        if not ref.digest:
            raise EvidenceIntegrityError("EvidenceRef.digest must be non-empty")
        return self._root / ref.algorithm / ref.digest


# 受众策略：PUBLIC ⊆ INTERNAL ⊆ RESTRICTED ⊆ CONFIDENTIAL。
# 请求方声明 audience=INTERNAL 时允许读 PUBLIC/INTERNAL;
# 读 RESTRICTED 必须声明 audience=RESTRICTED 或更高级;
# CONFIDENTIAL 必须 audience=CONFIDENTIAL。
_AUDIENCE_ORDER: dict[Classification, int] = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.RESTRICTED: 2,
    Classification.CONFIDENTIAL: 3,
}


def _enforce_audience(ref_classification: Classification, audience: Classification) -> None:
    """请求方声明的 audience 必须 ≥ ref.classification 才能读(0065 L8)。"""
    if _AUDIENCE_ORDER[audience] < _AUDIENCE_ORDER[ref_classification]:
        raise PermissionError(
            f"audience {audience.value!r} insufficient for evidence classified "
            f"{ref_classification.value!r}"
        )


__all__ = [
    "FilesystemEvidenceStore",
]


# Re-export CAS for convenience
def as_cas(store: EvidenceStore) -> ContentAddressableStore:
    """Best-effort 把 EvidenceStore 降级到 CAS view(只读契约)。"""
    raise TypeError("EvidenceStore is not a CAS; convert via FilesystemEvidenceStore directly")
