"""P0-09 — ADR-0195 O6 / ADR-0194 G1: obs journal hotpath 调用基线。

``append_journal_event`` 在 ``lca/cognition/`` 与 ``lca/loop/`` 的调用次数
不得高于 baseline — 新代码应经 ``FactGateway`` / loop 缝写入,不得扩散
journal 热路径直连。

当前 baseline(2026-09-06,P0-09 骨架,P1-16 cognition fact isolation):
  lca/cognition: 0 occurrences
  lca/loop:       6 occurrences
  total:          6
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS: tuple[Path, ...] = (
    _REPO_ROOT / "lca" / "cognition",
    _REPO_ROOT / "lca" / "loop",
)

# rg-equivalent count baseline; decrease intentionally → lower constant + note in PR.
_APPEND_JOURNAL_EVENT_BASELINE = 6


def _count_append_journal_event() -> int:
    total = 0
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                total += py.read_text(encoding="utf-8").count("append_journal_event")
            except (OSError, UnicodeDecodeError):
                continue
    return total


def test_append_journal_event_count_does_not_increase() -> None:
    """journal 热路径调用不得高于 baseline。"""
    current = _count_append_journal_event()
    assert current <= _APPEND_JOURNAL_EVENT_BASELINE, (
        f"append_journal_event count increased: {current} > baseline {_APPEND_JOURNAL_EVENT_BASELINE}. "
        "新调用应走 FactGateway/loop 缝;若迁移减少,同步降低 _APPEND_JOURNAL_EVENT_BASELINE。"
    )


def test_append_journal_event_baseline_is_current() -> None:
    """baseline 常量与现状一致,防止只增不减的漂移。"""
    current = _count_append_journal_event()
    assert current == _APPEND_JOURNAL_EVENT_BASELINE, (
        f"append_journal_event count dropped to {current}; "
        f"update _APPEND_JOURNAL_EVENT_BASELINE from {_APPEND_JOURNAL_EVENT_BASELINE} "
        "when migration intentionally reduces hotpath usage."
    )
