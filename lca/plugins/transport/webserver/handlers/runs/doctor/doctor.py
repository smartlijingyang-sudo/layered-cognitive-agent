"""Stable Gateway doctor.v3 facade(ADR-0164 草案 Phase 4)。

路由策略:
    - ``journal.json`` (.json / .jsonl → .json) → ``diagnose_step_tree``
    - ``journal.jsonl`` (.jsonl 旧格式) → ``diagnose_legacy``(保留回退)
    - Session Spine 路径 → ``diagnose_session_projection``(沿用)

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
from lca.plugins.transport.webserver.handlers.runs.doctor.legacy import diagnose_legacy
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
    jsonl_path: Path,
    *,
    mode: DoctorMode = "backend",
) -> DoctorReport:
    """诊断 run → doctor.v3。

    路由规则:
      - ``jsonl_path`` 指向 ``.json``(step-tree) → ``diagnose_step_tree``。
      - 指向 ``.jsonl``(legacy) → ``diagnose_legacy``(返回 v2 风格报告,
        schema 标记为 "doctor.v3" 但 hops 是 v2 子集)。
    """
    if jsonl_path.suffix == ".json":
        return diagnose_step_tree(jsonl_path, mode=mode)
    return diagnose_legacy(session, jsonl_path)


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
