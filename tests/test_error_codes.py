"""ErrorCode 字典 + diagnose alias 测试(ADR-0065 §六 / PR-9)。"""

from __future__ import annotations

from enum import Enum

from lca.contracts.observability.error_codes import (
    DIAGNOSE_ALIASES,
    DIAGNOSE_HINTS,
    ErrorCategory,
    ErrorCode,
    category_of,
)


def test_error_code_enum_is_closed() -> None:
    """枚举封闭集;新增必须 ADR 评审。"""
    members = set(ErrorCode)
    assert len(members) >= 24  # 10 大类 ~30 码(实际 26)
    # 验证代表性 code 存在
    assert ErrorCode.LLM_RATE_LIMIT in members
    assert ErrorCode.LOOP_STUCK in members
    assert ErrorCode.USER_CANCELLED in members


def test_error_category_enum_has_10_categories() -> None:
    assert len(ErrorCategory) == 10
    assert ErrorCategory.LLM in set(ErrorCategory)
    assert ErrorCategory.USER in set(ErrorCategory)


def test_category_of_maps_each_code() -> None:
    for code in ErrorCode:
        cat = category_of(code)
        assert isinstance(cat, ErrorCategory)


def test_category_of_unknown_code_raises() -> None:
    class FakeCode(str, Enum):
        FAKE = "fake"

    with __import__("pytest").raises(ValueError):
        category_of(FakeCode.FAKE)  # type: ignore[arg-type]


def test_diagnose_aliases_have_four_required() -> None:
    """0064 §9 起步:model_not_seen / loop_stuck / memory_poisoned / approval_rejected。"""
    assert "model_not_seen" in DIAGNOSE_ALIASES
    assert "loop_stuck" in DIAGNOSE_ALIASES
    assert "memory_poisoned" in DIAGNOSE_ALIASES
    assert "approval_rejected" in DIAGNOSE_ALIASES
    assert len(DIAGNOSE_ALIASES) == 4


def test_diagnose_aliases_have_hints() -> None:
    for alias in DIAGNOSE_ALIASES:
        assert alias in DIAGNOSE_HINTS
        assert len(DIAGNOSE_HINTS[alias]) > 0


def test_model_not_seen_alias_contains_llm() -> None:
    codes = DIAGNOSE_ALIASES["model_not_seen"]
    assert ErrorCode.LLM_MODEL_NOT_FOUND in codes
    assert ErrorCode.PLUGIN_BOOT_FAILED in codes
    # 至少含 LLM category
    assert any(category_of(c) == ErrorCategory.LLM for c in codes)


def test_loop_stuck_alias_maps_to_loop() -> None:
    codes = DIAGNOSE_ALIASES["loop_stuck"]
    assert all(category_of(c) == ErrorCategory.LOOP for c in codes)
