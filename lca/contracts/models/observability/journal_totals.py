"""Totals / SegmentRecord / PhaseRecord / StepPhase —— lca.journal/3.1 三层计数。

ADR-0166 D1 / D2 落地（step = DSH「一次模型请求 + 其工具」；segment = think|act；
phase = 闭集相位含 perceive）。三类元数据入主路径：

- ``totals``       —— JournalDocument 顶层，**单一真理**用于 reader / doctor。
- ``phases``       —— PhaseRecord 显式数组，包含 perceive（perceive 不开 step）。
- ``segments``     —— SegmentRecord 在每个 JournalStep 内，think|act 计数。

读旧 ``lca.journal/3`` 文档时这三字段均为缺省；migrator 把 phase-as-step
折叠为 DSH step，并显式构造 totals / phases / segments。

``StepPhase`` 在此定义（独立 enum，避开 journal_step ↔ journal_totals
循环依赖）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StepPhase = Literal["perceive", "think", "act", "reflect", "remember", "stop"]


@dataclass(frozen=True)
class Totals:
    """``JournalDocument.totals`` —— 三层计数的唯一真理。

    - ``steps``     : JournalDocument.steps 长度
    - ``segments``  : sum(len(s.segments) for s in steps)
    - ``phases``    : len(JournalDocument.phases)  —— 显式相位数组长度

    不变量：
    - totals.steps == len(steps)
    - totals.segments == sum(len(s.segments) for s in steps)
                == len([p for p in phases if p.kind in ("think", "act")])
    - totals.phases == len(phases)
    """

    steps: int = 0
    segments: int = 0
    phases: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"steps": self.steps, "segments": self.segments, "phases": self.phases}


@dataclass(frozen=True)
class SegmentRecord:
    """一段 think / act 的事实记录（ADR-0166 D2）。"""

    segment_id: str
    kind: str  # "think" | "act"
    phase_ref: str | None = None  # 指回 phases[]
    started_at: int = 0
    ended_at: int | None = None
    outcome: str | None = None  # "ok" | "fail" | "skip"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseRecord:
    """一个闭集相位的事实记录（ADR-0166 D2）。"""

    phase_id: str
    kind: StepPhase
    step_id: str | None = None  # perceive 可在 step 打开前为 None
    segment_id: str | None = None
    entered_at: int = 0
    exited_at: int | None = None
    summary: str | None = None
    outcome: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
