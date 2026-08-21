"""Diagnose aliases —— ADR-0065 §六 / PR-9。

``lca-ops diagnose <alias>`` 4 个内置别名:
- ``model_not_seen`` → LLM_MODEL_NOT_FOUND / PLUGIN_BOOT_FAILED
- ``loop_stuck`` → LOOP_STUCK / LOOP_OSCILLATING / LOOP_MAX_STEPS
- ``memory_poisoned`` → MEMORY_POISONED / MEMORY_FULL
- ``approval_rejected`` → GATE_DENIED / TOOL_PERMISSION_DENIED / AUTH_INSUFFICIENT

每个别名返回可执行的修复建议(由 ``DIAGNOSE_HINTS`` 提供)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.observability.error_codes import (
    DIAGNOSE_ALIASES,
    DIAGNOSE_HINTS,
    ErrorCode,
)


@dataclass(frozen=True)
class DiagnoseReport:
    """diagnose 别名的输出报告。"""

    alias: str
    error_codes: tuple[ErrorCode, ...]
    hint: str
    extra: dict[str, Any] = field(default_factory=dict)


def diagnose_alias(alias: str) -> DiagnoseReport:
    """查询一个内置 alias;alias 缺失抛 KeyError。"""
    codes = DIAGNOSE_ALIASES.get(alias)
    if codes is None:
        raise KeyError(f"unknown diagnose alias: {alias!r}; valid: {sorted(DIAGNOSE_ALIASES)}")
    hint = DIAGNOSE_HINTS.get(alias, "")
    return DiagnoseReport(alias=alias, error_codes=codes, hint=hint)


def list_diagnose_aliases() -> tuple[str, ...]:
    """所有内置 diagnose alias;按注册顺序。"""
    return tuple(DIAGNOSE_ALIASES.keys())


__all__ = ["DiagnoseReport", "diagnose_alias", "list_diagnose_aliases"]
