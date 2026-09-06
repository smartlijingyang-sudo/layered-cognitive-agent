"""P0-08 — ADR-0195 §7 P-L2: ``lca/plugins/transport/`` 零认知/事实热路径 import。

不变量:transport carrier/read/wire 不得 import 或调用 ``Session.append``、
``Reducer``、``PhaseExecutor``、``GenericPlanInterpreter`` — 这些是 loop/runtime
专属面,transport 只触发 run 与读投影。

本测试记录已知 offenders 为 baseline,仅对**新增**违规 fail-fast;
清零后移除 ``@pytest.mark.xfail`` 的 strict 目标测试。

当前 baseline(2026-09-06,P0-08 骨架): 0 files。
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOT = _REPO_ROOT / "lca" / "plugins" / "transport"

# P-L2 禁止 import/调用的符号。
_FORBIDDEN_SYMBOLS: tuple[str, ...] = (
    "Session.append",
    "Reducer",
    "PhaseExecutor",
    "GenericPlanInterpreter",
)

_IMPORT_LINE = re.compile(r"^\s*(from\s+\S+\s+import|import\s+\S+)")

# 已知债(2026-09-06): transport 尚无代码级违规;注释/README 不计入。
_BASELINE_OFFENDERS: frozenset[str] = frozenset()


def _code_line(line: str) -> str:
    """Strip full-line and inline ``#`` comments for pattern matching."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line.split("#", 1)[0]


def _line_violates(code: str) -> bool:
    if not code.strip():
        return False
    if "Session.append" in code:
        return True
    if not _IMPORT_LINE.match(code):
        return False
    return any(symbol in code for symbol in _FORBIDDEN_SYMBOLS[1:])


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
        if any(_line_violates(_code_line(line)) for line in lines):
            offenders.add(py.relative_to(_REPO_ROOT).as_posix())
    return frozenset(offenders)


def test_transport_directory_exists() -> None:
    """sanity:transport 目录缺失时 fail-loud。"""
    assert _SCAN_ROOT.exists(), f"transport directory missing: {_SCAN_ROOT}"


def test_transport_no_new_isolation_violations() -> None:
    """baseline 守护:禁止在已知债之外新增 P-L2 import/usage。"""
    current = _find_offenders()
    new_offenders = sorted(current - _BASELINE_OFFENDERS)
    assert not new_offenders, (
        "ADR-0195 P-L2 新增违规:lca/plugins/transport/** 出现新的禁止 import/usage:\n"
        + "\n".join(f"  - {p}" for p in new_offenders)
        + "\n若属已知迁移债,更新 _BASELINE_OFFENDERS 并附 delete-when。"
    )


def test_transport_has_no_isolation_violations_strict() -> None:
    """strict 目标:transport 零 P-L2 违规(2026-09-06 已达成)。"""
    offenders = sorted(_find_offenders())
    assert offenders == [], (
        "ADR-0195 P-L2 违规:lca/plugins/transport/** 含禁止 import/usage:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )
