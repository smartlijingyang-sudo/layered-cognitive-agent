"""P0-07 — ADR-0194 §7 L1 / ADR-0195 §5: ``lca/cognition/`` 零事实生产 import。

不变量:认知原语只产出 Decision/Observation/Manifest,不得直接 import 或调用
``spine_reflector`` / ``append_journal_event`` / ``Session.append`` /
``fact_gateway`` / ``plugins.events.publishers`` 等事实生产面。

本测试记录已知 offenders 为 baseline,仅对**新增**违规文件 fail-fast;
清零后移除 ``@pytest.mark.xfail`` 的 strict 目标测试。

当前 baseline(2026-09-06,P0-07 骨架,P1-13): 10 files — 见 ``_BASELINE_OFFENDERS``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

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

# 已知债:迁移至 ``lca/loop/fact_gateway`` 前不得新增。
_BASELINE_OFFENDERS: frozenset[str] = frozenset(
    {
        "lca/cognition/_spine_envelope.py",
        "lca/cognition/body/action_handlers.py",
        "lca/cognition/body/delegation_cache.py",
        "lca/cognition/body/safe_executor.py",
        "lca/cognition/body/team_message_tool.py",
        "lca/cognition/body/tool_journal_emit.py",
        "lca/cognition/brain/null_critic.py",
        "lca/cognition/brain/reasoner.py",
        "lca/cognition/brain/skill_router.py",
        "lca/cognition/brain/synthesizer.py",
    }
)


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


@pytest.mark.xfail(
    strict=False,
    reason="existing offenders: 10 files — see _BASELINE_OFFENDERS for roadmap",
)
def test_cognition_has_no_fact_production_imports_strict() -> None:
    """strict 目标:offenders 清零后 xpass,随后移除 xfail marker。"""
    offenders = sorted(_find_offenders())
    assert offenders == [], (
        "ADR-0194 §7 L1 违规:lca/cognition/** 含事实生产面 import/usage:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )
