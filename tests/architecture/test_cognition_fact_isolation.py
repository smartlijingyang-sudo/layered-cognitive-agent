"""P0-07 — ADR-0194 §7 L1 / ADR-0195 §5: ``lca/cognition/`` 零事实生产 import。

不变量:认知原语只产出 Decision/Observation/Manifest,不得直接 import 或调用
``spine_reflector`` / ``append_journal_event`` / ``Session.append`` /
``fact_gateway`` / ``plugins.events.publishers`` 等事实生产面。

本测试记录已知 offenders 为 baseline,仅对**新增**违规文件 fail-fast;
P1-16 清零后 strict 测试为常规 pass。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOT = _REPO_ROOT / "lca" / "cognition"

# ADR-0194 §7 L1 禁止的事实生产面词表(import / 直接调用)。
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "spine_reflector",
    "append_journal_event",
    "Session.append",
    "fact_gateway",
    "FactGateway",
    "plugins.events.publishers",
)

# 迁移债清零(P1-16);保留空 baseline 供新增违规 fail-fast。
_BASELINE_OFFENDERS: frozenset[str] = frozenset()


def _code_line(line: str) -> str:
    """Strip full-line and inline ``#`` comments for pattern matching."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line.split("#", 1)[0]


def _find_offenders() -> frozenset[str]:
    offenders: set[str] = set()
    if not _SCAN_ROOT.exists():
        return frozenset()
    for py in sorted(_SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern in _code_line(line) for line in lines for pattern in _FORBIDDEN_PATTERNS):
            offenders.add(py.relative_to(_REPO_ROOT).as_posix())
    return frozenset(offenders)


def test_cognition_directory_exists() -> None:
    """sanity:认知目录迁移/重命名时 fail-loud。"""
    assert _SCAN_ROOT.exists(), f"cognition directory missing: {_SCAN_ROOT}"


def test_cognition_no_new_fact_production_imports() -> None:
    """baseline 守护:禁止在已知债之外新增事实生产面 import/usage。"""
    current = _find_offenders()
    new_offenders = sorted(current - _BASELINE_OFFENDERS)
    assert not new_offenders, (
        "ADR-0194 §7 L1 新增违规:lca/cognition/** 出现新的事实生产面 import/usage:\n"
        + "\n".join(f"  - {p}" for p in new_offenders)
        + "\n若属已知迁移债,更新 _BASELINE_OFFENDERS 并附 delete-when。"
    )


def test_cognition_has_no_fact_production_imports_strict() -> None:
    """strict 目标:offenders 清零(P1-16)。"""
    offenders = sorted(_find_offenders())
    assert offenders == [], (
        "ADR-0194 §7 L1 违规:lca/cognition/** 含事实生产面 import/usage:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )
