"""Stable Gateway doctor.v3 facade(ADR-0164 草案 Phase 4)。

路由策略:
    - ``journal.json`` (step-tree) → ``diagnose_step_tree``
    - Session Spine 路径 → ``diagnose_session_projection``(沿用)

新 boot 只产 spine ledger (SSOT) + ``journal.json`` (step-tree
materialization)。 ``journal.jsonl`` / ``journal.raw.jsonl`` 旧流式路径已
彻底移除;doctor 不再保留 legacy fallback,非 step-tree 路径直接报错。

升级要点:
    - schema 从 "doctor.v2" → "doctor.v3"。
    - 增 mode 字段("backend" / "ui")。
    - 增 H8 "步骤因果链完整性"。
    - H4/H5 在 mode=backend 时显式 skipped, 不再永远 ok=None。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.harness.state.projection import ProjectionSnapshot
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    DoctorMode,
    DoctorReport,
    HopVerdict,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.session_check import (
    diagnose_session_projection,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.step_check import (
    diagnose_step_tree,
)


def diagnose(
    session: Any | None,
    journal_path: Path,
    *,
    mode: DoctorMode = "backend",
) -> DoctorReport:
    """诊断 run → doctor.v3。

    路由规则:
      - ``.json`` → ``diagnose_step_tree``(完整 step-tree 检查)。
      - ``.jsonl`` → spine ledger(SSOT)兜底:journal.json 缺失,
        doctor 报告一个 H1=False 的最小诊断,不再回退到 legacy v2 hops。

    旧 ``journal.jsonl`` 流式布局已下线:该后缀只允许指向当前 boot 产出的
    spine ledger(SSOT),不接受历史 journal.jsonl 流。
    """
    del session  # step-tree 路径不需要 live session;保留签名以避免调用方改动
    if journal_path.suffix == ".json":
        return diagnose_step_tree(journal_path, mode=mode)
    if journal_path.suffix == ".jsonl":
        return _diagnose_spine_only(journal_path, mode=mode)
    raise ValueError(
        f"doctor.diagnose expects journal.json (step-tree) or spine ledger, "
        f"got suffix {journal_path.suffix!r}: {journal_path}"
    )


def _diagnose_spine_only(
    spine_path: Path,
    *,
    mode: DoctorMode,
) -> DoctorReport:
    """Step-tree materialization 缺失时的最小诊断。

    仅提供:
      - H1: journal.json 是否缺失 + spine ledger 状态
      - 其他 hop: ok=None "not evaluated" (无 step-tree,无法诊断)

    不复用 legacy v2 hops; 不解析 spine 内容(留给后续 spine-only 工具)。
    """
    run_id = spine_path.parent.name
    detail = (
        f"step-tree journal.json missing; spine ledger present at {spine_path}"
        if spine_path.exists()
        else f"journal materialization missing: spine ledger not found at {spine_path}"
    )
    return DoctorReport(
        schema="doctor.v3",
        run_id=run_id,
        trace_id="",
        status="unknown",
        outcome="unknown",
        broken_hop="H1",
        summary=detail,
        mode=mode,
        hops={
            "H1": HopVerdict(ok=False, detail=detail),
            "H2": HopVerdict(ok=None, detail="not evaluated (no step-tree)"),
            "H3": HopVerdict(ok=None, detail="not evaluated"),
            "H4": HopVerdict(ok=None, detail="not evaluated"),
            "H5": HopVerdict(ok=None, detail="not evaluated"),
            "H6": HopVerdict(ok=None, detail="not evaluated"),
            "H7": HopVerdict(ok=None, detail="not evaluated"),
            "H8": HopVerdict(ok=None, detail="not evaluated"),
            "H-seg": HopVerdict(ok=None, detail="not evaluated"),
            "H-phase": HopVerdict(ok=None, detail="not evaluated"),
            "H-xref": HopVerdict(ok=None, detail="not evaluated"),
            "H-ssot": HopVerdict(ok=None, detail="not evaluated"),
            "H-mv-journal": HopVerdict(ok=None, detail="not evaluated"),
        },
        journal_path=str(spine_path),
        consistency={},
        factory={"ok": True, "tools_missing_plugin_state": []},
    )


def diagnose_session(
    *,
    run_id: str,
    snapshot: ProjectionSnapshot,
    persisted_seq: int,
    persistence_ref: str,
    mode: DoctorMode = "backend",
) -> DoctorReport:
    """诊断 Session Spine run → doctor.v3。

    委托 session_check 现有实现 + mode 注入。 session_check.py 后续会
    升级以支持 step-tree read, 这里只把 schema/mode 透传过去。
    """
    report = diagnose_session_projection(
        run_id=run_id,
        snapshot=snapshot,
        persisted_seq=persisted_seq,
        persistence_ref=persistence_ref,
    )
    # 升级到 v3: schema + mode
    return DoctorReport(
        schema="doctor.v3",
        run_id=report.run_id,
        trace_id=report.trace_id,
        status=report.status,
        outcome=report.outcome,
        broken_hop=report.broken_hop,
        summary=report.summary,
        mode=mode,
        hops=report.hops,
        journal_path=report.journal_path,
        consistency=report.consistency,
        factory=report.factory,
    )


__all__ = [
    "DoctorMode",
    "DoctorReport",
    "HopVerdict",
    "diagnose",
    "diagnose_session",
    "diagnose_step_tree",
]
