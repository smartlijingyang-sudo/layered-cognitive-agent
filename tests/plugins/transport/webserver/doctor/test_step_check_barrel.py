"""Focused tests: step_check barrel re-export + hop dispatch(close-set 不变)。

覆盖:
  - ``lca.plugins.transport.webserver.doctor.step_check`` 仍是公共入口
    (re-export barrel),与 ``doctor.steps.diagnose`` 是同一函数对象。
  - ``diagnose_step_tree`` 的 hop 分发表覆盖完整 close-set:
    H1..H8 / H-seg / H-phase / H-xref / H-ssot / H-mv-journal / H-fold。
  - scan loop 经 barrel 在「journal 存在 / 不存在」两条路径都工作。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.plugins.transport.webserver.doctor.step_check import (
    diagnose_step_tree as barrel_diagnose_step_tree,
)
from lca.plugins.transport.webserver.doctor.steps.diagnose import (
    diagnose_step_tree as package_diagnose_step_tree,
)

HOP_NAMES = (
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "H7",
    "H8",
    "H-seg",
    "H-phase",
    "H-xref",
    "H-ssot",
    "H-mv-journal",
    "H-fold",
)


def test_barrel_reexports_implementation() -> None:
    """step_check 是 barrel:与 steps.diagnose 是同一函数对象。"""
    assert barrel_diagnose_step_tree is package_diagnose_step_tree


def _write_minimal_journal(tmp_path: Path) -> Path:
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="t")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    doc = append_step(
        doc,
        JournalStep(
            step_id="s1",
            step_index=1,
            phase="think",
            entered_at=0.0,
            outcome="ok",
            reflect=ReflectTrace(summary="one step"),
        ),
    )
    doc = close_document(doc, outcome="completed", closed_at=1.0)
    path = tmp_path / "journal.json"
    JournalDocumentWriter(path).write(doc)
    return path


def test_dispatch_covers_full_hop_close_set(tmp_path: Path) -> None:
    """scan loop 经 barrel 返回完整 hop 集合(close-set 不变)。"""
    journal = _write_minimal_journal(tmp_path)
    report = barrel_diagnose_step_tree(journal)
    assert set(report.hops) == set(HOP_NAMES)
    assert report.hops["H1"].ok is True
    assert report.hops["H-fold"].ok is None  # 无 spine → not evaluated


def test_dispatch_scan_loop_missing_journal(tmp_path: Path) -> None:
    """journal.json 不存在时,barrel 仍返回完整 hop 集合且 H1 失败。"""
    report = barrel_diagnose_step_tree(tmp_path / "journal.json")
    assert set(report.hops) == set(HOP_NAMES)
    assert report.hops["H1"].ok is False
    assert report.broken_hop == "H1"
