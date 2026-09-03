"""RunManifest dataclass —— ADR-0065 §一 / §六 / PR-6。

终态事件提交后由 ``RunLedgerHandle.commit_terminal()`` 写出 ``manifest.json``。
它是 terminal materialization + 完整性状态,**不是事实 owner**(L6)。

字段:
- run_id / terminal_event_seq:导航身份(ADR-0096 I7: derived view 持 journal 主键,不持 hard event_id)
- ledger_high_watermark:生成时账本最后 run_seq
- ledger_summary:账本 sha256 摘要(可选;v1 无此字段)
- materializer_version:写 manifest 的版本(用 importlib.metadata 拿 lca 版本)
- evidence_integrity:每个 EvidenceRef 摘要校验状态
- started_at / closed_at:UTC 秒数
- pricing_ref:CostProjector 使用的版本化价目(若有)
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntegrityState(str, Enum):
    """evidence 完整性校验状态。"""

    OK = "ok"
    MISSING = "missing"  # ref 指向的对象不存在
    DIGEST_MISMATCH = "digest_mismatch"  # 摘要不匹配
    UNKNOWN = "unknown"  # backend 缺失或策略拒绝


@dataclass(frozen=True, slots=True)
class ManifestEvidence:
    """Manifest 中记录的 evidence 校验状态。"""

    ref_digest: str
    ref_algorithm: str
    state: IntegrityState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RunManifest:
    """terminal materialization(0065 §一 + L7)。

    ADR-0068 §决策二:``plan_ref`` 是 CompiledRunPlan 的 16-hex 稳定 ID,
    终端 manifest 必须以顶层字段携带(不是 ``extra.plan_ref``),
    让任何 reader 一行 grep 就能拿到图指纹、按 plan 复现/对比。
    """

    schema: str = "lca.run_manifest/1"
    run_id: str = ""
    plan_ref: str = ""  # ADR-0068 §决策二:CompiledRunPlan.plan_ref,16-hex 稳定 ID
    terminal_event_seq: int = 0
    ledger_high_watermark: int = 0
    ledger_summary: str = ""
    materializer_version: str = ""
    evidence_integrity: tuple[ManifestEvidence, ...] = ()
    started_at: float = 0.0
    closed_at: float = 0.0
    pricing_ref: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def materializer_default_version(cls) -> str:
        try:
            return importlib.metadata.version("lca-framework")
        except importlib.metadata.PackageNotFoundError:
            return "0.0.0+unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "plan_ref": self.plan_ref,
            "terminal_event_seq": self.terminal_event_seq,
            "ledger_high_watermark": self.ledger_high_watermark,
            "ledger_summary": self.ledger_summary,
            "materializer_version": self.materializer_version,
            "evidence_integrity": [
                {
                    "ref_digest": ei.ref_digest,
                    "ref_algorithm": ei.ref_algorithm,
                    "state": ei.state.value,
                    "detail": ei.detail,
                }
                for ei in self.evidence_integrity
            ],
            "started_at": self.started_at,
            "closed_at": self.closed_at,
            "pricing_ref": self.pricing_ref,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunManifest:
        integrity_raw = payload.get("evidence_integrity", ()) or ()
        integrity = tuple(
            ManifestEvidence(
                ref_digest=str(item.get("ref_digest", "")),
                ref_algorithm=str(item.get("ref_algorithm", "sha256")),
                state=IntegrityState(str(item.get("state", "unknown"))),
                detail=str(item.get("detail", "")),
            )
            for item in integrity_raw
            if isinstance(item, Mapping)
        )
        return cls(
            schema=str(payload.get("schema", "lca.run_manifest/1")),
            run_id=str(payload.get("run_id", "")),
            plan_ref=str(payload.get("plan_ref", "")),
            terminal_event_seq=int(payload.get("terminal_event_seq", 0)),
            ledger_high_watermark=int(payload.get("ledger_high_watermark", 0)),
            ledger_summary=str(payload.get("ledger_summary", "")),
            materializer_version=str(payload.get("materializer_version", "")),
            evidence_integrity=integrity,
            started_at=float(payload.get("started_at", 0.0)),
            closed_at=float(payload.get("closed_at", 0.0)),
            pricing_ref=str(payload.get("pricing_ref", "")),
            extra=dict(payload.get("extra", {}) or {}),
        )


__all__ = [
    "IntegrityState",
    "ManifestEvidence",
    "RunManifest",
]
