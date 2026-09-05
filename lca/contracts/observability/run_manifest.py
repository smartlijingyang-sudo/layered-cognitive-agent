"""RunManifest dataclass —— ADR-0065 §一 / §六 / PR-6。

终态事件提交后由 ``RunLedgerHandle.commit_terminal()`` 写出 ``manifest.json``。
它是 terminal materialization + 完整性状态,**不是事实 owner**(L6)。

字段:
- run_id / terminal_event_seq:导航身份(ADR-0096 I7: derived view 持 journal 主键,不持 hard event_id)
- ledger_high_watermark:生成时账本最后 run_seq
- ledger_summary:账本 sha256 摘要(可选;v1 无此字段)
- started_at / closed_at:UTC 秒数

P3(slim):删 ``materializer_version`` / ``evidence_integrity`` / ``pricing_ref``;
前两者从未在 reader 中被消费,后者语义与 ``CostProjector.pricing_ref``
(``lca/contracts/observability/cost.py``)无关 —— manifest 字段空串从未承载真值。
"""

from __future__ import annotations

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
    session_error: str = ""  # 终态 carrier 错误;顶层可读(ADR-0165.1 / ADR-0122)
    session_status: str = ""  # RunSession.status.value 物化快照
    terminal_event_seq: int = 0
    ledger_high_watermark: int = 0
    ledger_summary: str = ""
    started_at: float = 0.0
    closed_at: float = 0.0
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "plan_ref": self.plan_ref,
            "session_error": self.session_error,
            "session_status": self.session_status,
            "terminal_event_seq": self.terminal_event_seq,
            "ledger_high_watermark": self.ledger_high_watermark,
            "ledger_summary": self.ledger_summary,
            "started_at": self.started_at,
            "closed_at": self.closed_at,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunManifest:
        extra = dict(payload.get("extra", {}) or {})
        return cls(
            schema=str(payload.get("schema", "lca.run_manifest/1")),
            run_id=str(payload.get("run_id", "")),
            plan_ref=str(payload.get("plan_ref", "")),
            session_error=str(payload.get("session_error") or extra.get("session_error") or ""),
            session_status=str(payload.get("session_status") or extra.get("session_status") or ""),
            terminal_event_seq=int(payload.get("terminal_event_seq", 0)),
            ledger_high_watermark=int(payload.get("ledger_high_watermark", 0)),
            ledger_summary=str(payload.get("ledger_summary", "")),
            started_at=float(payload.get("started_at", 0.0)),
            closed_at=float(payload.get("closed_at", 0.0)),
            extra=extra,
        )


__all__ = [
    "IntegrityState",
    "ManifestEvidence",
    "RunManifest",
]
