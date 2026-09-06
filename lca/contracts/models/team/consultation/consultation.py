"""ConsultationOutcome — board/consult 证据平面（ADR-0049）。

与 MemberStatus（进度控制面）正交：
- status 回答「还要不要再问」
- outcomes 回答「已经拿到什么可综合的证据」
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ConsultationDisposition(str, Enum):
    """一次咨询尝试的结局类别。"""

    COMPLETED = "completed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    VALIDATION_FAILED = "validation_failed"
    ERROR = "error"


class SynthesisMethod(str, Enum):
    """board 收口方法——按证据完备度命名（非门闩开合）。"""

    FULL = "full"
    PARTIAL = "partial"
    SOLO_FALLBACK = "solo_fallback"


# 向后兼容 journal / 旧断言中的历史 method 名
SYNTHESIS_METHOD_ALL_CONSULTED_LEGACY = "all_consulted"


@dataclass(frozen=True)
class ConsultationOutcome:
    """一次委派咨询的证据记录。"""

    outcome_id: str
    role: str
    attempt: int
    disposition: ConsultationDisposition
    evidence: str | None
    usable: bool
    failure_kind: str | None
    task_id: str | None
    delegation_id: str | None
    step: int
    returned_at: datetime
    subtask: str = ""
    error: str | None = None
    latency_ms: int = 0


def latest_outcome_for_role(
    outcomes: Sequence[ConsultationOutcome], role: str
) -> ConsultationOutcome | None:
    """返回某角色最近一次 outcome（attempt 最大，并列取末条）。"""
    matched = [o for o in outcomes if o.role == role]
    if not matched:
        return None
    return max(matched, key=lambda o: (o.attempt, o.returned_at))


def usable_outcomes(outcomes: Sequence[ConsultationOutcome]) -> list[ConsultationOutcome]:
    """可进入综合的证据（每角色取最新 usable）。"""
    by_role: dict[str, ConsultationOutcome] = {}
    for outcome in outcomes:
        if not outcome.usable:
            continue
        prev = by_role.get(outcome.role)
        if prev is None or outcome.attempt >= prev.attempt:
            by_role[outcome.role] = outcome
    return list(by_role.values())


def build_evidence_pack_text(outcomes: Sequence[ConsultationOutcome]) -> str:
    """渲染 lead 综合用的证据包文本。"""
    usable = usable_outcomes(outcomes)
    if not usable:
        return "（无可用成员证据——需以 lead 自身知识兜底）"
    lines: list[str] = []
    for item in sorted(usable, key=lambda o: o.role):
        quality = "完整" if item.disposition == ConsultationDisposition.COMPLETED else "部分"
        body = (item.evidence or "").strip()
        lines.append(f"### {item.role}（{quality}）\n{body}")
    return "\n\n".join(lines)
