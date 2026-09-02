"""Regression guard for ADR-0165-i17-traceback-and-coverage (close-set whitelist).

Legacy ``RUN_FINISHED_EVENTS`` + ``scan_jsonl`` paths 已下线:doctor H2 现在读
step-tree ``JournalDocument.outcome`` / ``metadata.closed_at``(见
``step_check.py::_hop_h2``)。 本文件保留 EP close-set 白名单测试,确保新
journal execution_points 进入消费侧 union 集合。
"""

from __future__ import annotations

from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS


def test_execution_points_whitelist_admits_new_eps() -> None:
    """New journal EPs from the ADR are part of the close-set whitelist."""
    assert "spine.i17.rejected" in EXECUTION_POINTS
    assert "spine.producer.failure" in EXECUTION_POINTS
    assert "phase_graph.instrument.coverage" in EXECUTION_POINTS
