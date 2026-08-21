"""Diagnose aliases 测试(ADR-0065 §六 / PR-9)。"""

from __future__ import annotations

import pytest

from lca.contracts.observability.error_codes import ErrorCode
from lca.harness.diagnostics.diagnose import (
    DiagnoseReport,
    diagnose_alias,
    list_diagnose_aliases,
)


def test_diagnose_alias_known() -> None:
    report = diagnose_alias("loop_stuck")
    assert isinstance(report, DiagnoseReport)
    assert report.alias == "loop_stuck"
    assert ErrorCode.LOOP_STUCK in report.error_codes
    assert "max_steps" in report.hint or "step" in report.hint


def test_diagnose_alias_unknown_raises() -> None:
    with pytest.raises(KeyError):
        diagnose_alias("nonexistent_alias")


def test_list_diagnose_aliases_returns_four() -> None:
    aliases = list_diagnose_aliases()
    assert len(aliases) == 4
    assert "model_not_seen" in aliases
    assert "loop_stuck" in aliases
    assert "memory_poisoned" in aliases
    assert "approval_rejected" in aliases


def test_all_aliases_have_non_empty_hints() -> None:
    for alias in list_diagnose_aliases():
        report = diagnose_alias(alias)
        assert len(report.hint) > 10
        assert len(report.error_codes) > 0
